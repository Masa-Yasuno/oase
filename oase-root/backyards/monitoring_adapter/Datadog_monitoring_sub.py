# Copyright 2019 NEC Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
[概要]
  監視アダプタ 監視実行処理（子プロセス）
"""

import os
import sys
import json
import re
import pytz
import datetime
import django
import traceback

from socket import gethostname

# OASE モジュール importパス追加
my_path = os.path.dirname(os.path.abspath(__file__))
tmp_path = my_path.split('oase-root')
root_dir_path = tmp_path[0] + 'oase-root'
sys.path.append(root_dir_path)

# OASE モジュール import
# #LOCAL_PATCH#
os.environ['DJANGO_SETTINGS_MODULE'] = 'confs.frameworkconfs.settings'
django.setup()

from django.conf import settings
from django.db import transaction
from django.db.models import Q

#################################################
# デバック用
if settings.DEBUG and getattr(settings, 'ENABLE_NOSERVICE_BACKYARDS', False):
    oase_root_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../..')
    os.environ['OASE_ROOT_DIR'] = oase_root_dir 
    os.environ['RUN_INTERVAL']  = '3'
    os.environ['PYTHON_MODULE'] = '/usr/bin/python3'
    os.environ['LOG_LEVEL']     = "TRACE"
    os.environ['LOG_DIR']       = oase_root_dir + "/logs/backyardlogs/oase_monitoring"
#################################################
# 環境変数取得
try:
    root_dir_path = os.environ['OASE_ROOT_DIR']
    run_interval  = os.environ['RUN_INTERVAL']
    python_module = os.environ['PYTHON_MODULE']
    log_dir       = os.environ['LOG_DIR']
    log_level     = os.environ['LOG_LEVEL']
except Exception as ex:
    print(str(ex))
    sys.exit(2)

# ロガー初期化
from libs.commonlibs.oase_logger import OaseLogger
logger = OaseLogger.get_instance()


#################################################
# 負荷テスト設定
ENABLE_LOAD_TEST = getattr(settings, 'ENABLE_LOAD_TEST', False)
if ENABLE_LOAD_TEST:
    import time
    import logging
    loadtest_logger = logging.getLogger('oase_action_sub')


from web_app.models.models import User
from web_app.models.models import System
from web_app.models.models import RuleType
from web_app.models.models import MonitoringType
from web_app.models.models import AdapterType
from web_app.models.Datadog_monitoring_models import DatadogAdapter
from web_app.models.Datadog_monitoring_models import DatadogMonitoringHistory, DatadogMatchInfo
from web_app.templatetags.common import get_message

from libs.backyardlibs.monitoring_adapter.Datadog.manage_trigger import ManageTrigger
from libs.backyardlibs.monitoring_adapter.Datadog.Datadog_api import DatadogApi
from libs.backyardlibs.monitoring_adapter.Datadog.Datadog_formatting import message_formatting
from libs.backyardlibs.monitoring_adapter.Datadog.Datadog_request import send_request
from libs.commonlibs.common import Common
from libs.commonlibs.define import *


#-------------------
# STATUS
#-------------------
PROCESSING   = 1
PROCESSED    = 2
SERVER_ERROR = 3

DB_OASE_USER = -2140000010


class DatadogAdapterSubModules:
    """
    [クラス概要]
        Datadogアダプタメイン処理クラス
    """

    def __init__(self, datadog_adapter_id=0):
        """
        [概要]
          コンストラクタ
        """

        # クラス生成
        self.datadog_adapter_id = datadog_adapter_id
        self.datadog_adapter = None
        self.monitoring_history = None
        self.user_objects = User.objects.get(user_id=DB_OASE_USER)
        self.user = self.user_objects.user_name


    def insert_monitoring_history(self, datadog_lastchange, status):
        """
        [概要]
          Datadog監視履歴登録メゾット
        """
        logger.logic_log(
            'LOSI00001', 'datadog_adapter_id: %s, datadog_lastchange: %s, status: %s' %
            (self.datadog_adapter_id, datadog_lastchange, status))

        monitoring_history = None
        monitoring_history_id = -1
        try:
            with transaction.atomic():

                monitoring_history = DatadogMonitoringHistory(
                    datadog_adapter_id    = self.datadog_adapter_id,
                    datadog_lastchange    = datadog_lastchange,
                    status                = status,
                    status_update_id      = gethostname(),
                    last_update_timestamp = datetime.datetime.now(pytz.timezone('UTC')),
                    last_update_user      = self.user,
                )
                monitoring_history.save(force_insert=True)

                monitoring_history_id = monitoring_history.pk

        except Exception as e:
            logger.system_log('LOSM38018', 'OASE_T_DATADOG_MONITORING_HISTORY')
            logger.logic_log('LOSM00001', 'Traceback: %s' % (traceback.format_exc()))
            monitoring_history = None

        logger.logic_log('LOSI00002', 'monitoring_history_id: %s' % (str(monitoring_history_id)))

        return monitoring_history


    def update_monitoring_history(self, status, last_monitoring_time):
        """
        [概要]
          Datadog監視履歴更新メゾット
        """

        logger.logic_log('LOSI00001', 'status: %s' % (status))
        try:
            with transaction.atomic():
                self.monitoring_history.status = status
                self.monitoring_history.datadog_lastchange = last_monitoring_time
                self.monitoring_history.status_update_id = gethostname()
                self.monitoring_history.last_update_timestamp = datetime.datetime.now(pytz.timezone('UTC'))
                self.monitoring_history.last_update_user = self.user
                self.monitoring_history.save(force_update=True)

        except Exception as e:
            raise

        logger.logic_log('LOSI00002', 'None')
        return True


    def execute(self, datadog_adapter, from_dt, to_dt):
        """
        [概要]
          監視実行
        """

        logger.logic_log('LOSI00001', datadog_adapter.datadog_adapter_id)

        result = True
        api_response = []
        last_monitoring_time = to_dt
        to_dt = self.convert_epoch_time(to_dt)

        try:
            datadog_api = DatadogApi(datadog_adapter)
            # TODO last_monitoring_timeを返却してもらう予定 現状(2020/01/10) 0で実施する
            api_response, flg = datadog_api.get_active_triggers(from_dt, to_dt)
            if flg:
                with transaction.atomic():
                    comp_dd_adap = DatadogAdapter.objects.select_for_update().get(datadog_adapter_id=datadog_adapter.datadog_adapter_id)
                    if datadog_adapter.last_update_timestamp == comp_dd_adap.last_update_timestamp:
                        comp_dd_adap.status_flag = 1
                        comp_dd_adap.last_update_timestamp = datetime.datetime.now(pytz.timezone('UTC'))
                        comp_dd_adap.save(force_update=True)
                
                result = False
                api_response = []
                last_monitoring_time = last_monitoring_time

        except TypeError as e:
            result = False
            logger.system_log('LOSM38019', 'Datadog')
            logger.logic_log('LOSM00001', 'e: %s' % (e))

        except Exception as e:
            result = False
            logger.system_log('LOSM38019', 'Datadog')
            logger.logic_log('LOSM00001', 'e: %s, Traceback: %s' % (e, traceback.format_exc()))

        logger.logic_log('LOSI00002', 'None')

        return result, api_response, last_monitoring_time


    def _parser(self, idx, data_tmp, key_list, parse_list):

        while idx < len(key_list):
            k = key_list[idx]
            l = len(k)

            # 配列走査する場合
            if l == 2 and k.startswith('[') and k.endswith(']'):
                idx = idx + 1
                for dt in data_tmp:
                    result = self._parser(idx, dt, key_list, parse_list)
                    if not result:
                        return False

                else:
                    break

            # 配列型の添え字の場合
            elif l > 2 and k.startswith('[') and k.endswith(']'):
                # 要素の値が数値ではない
                if k[1 : l - 1].isdigit() == False:
                    logger.system_log('LOSM38013', 'element:%s' % (k[1 : l - 1]))
                    return False

                i = int(k[1 : l - 1])

                # 抽出データが配列型ではない、もしくは、要素数が不足
                if isinstance(data_tmp, list) == False or i >= len(data_tmp):
                    logger.system_log('LOSM38012', 'data_tmp:%s, index:%s, records:%s' % (data_tmp, i, len(data_tmp)))
                    return False

                data_tmp = data_tmp[i]
                idx = idx + 1

            # 辞書型のキーの場合
            if not (k.startswith('[') and k.endswith(']')):

                # 抽出データが辞書型ではない、もしくは、キーが存在しない
                if isinstance(data_tmp,  dict) == False or k not in data_tmp:
                    logger.system_log('LOSM38011', 'data_tmp:%s, key:%s' % (data_tmp, k))
                    return False

                data_tmp = data_tmp[k]
                idx = idx + 1


        if idx >= len(key_list):
            parse_list.append(data_tmp)

        return True


    def convert_epoch_time(self, val):

        ret_val = val

        # エポック秒の場合は、整数に型キャスト
        try:
            ret_val = int(val)
            return ret_val

        except Exception as e:
            pass


        # 年月日がハイフン区切りの場合は、スラッシュ区切りに置換
        if re.match(r'^[0-9]{4}-([1-9]|0[1-9]|1[0-2])-([1-9]|0[1-9]|[12][0-9]|3[01])', val):
            val = val.replace('-', '/', 2)

        # アルファベットを削除
        val = val.replace('T', ' ')
        val = val.replace('Z', '')

        # タイムゾーンの補正値が含まれる場合は、時分の値を取得
        hours   = 0
        minutes = 0
        if re.match(r'.*[+-]([0-1][0-9]|2[0-3])\:[0-5][0-9]$', val):
            val_tmp = (re.split('[+-]', val))[1]
            hours   = int(val_tmp.split(':')[0])
            minutes = int(val_tmp.split(':')[1])

            if '+' in val:
                hours   = hours   * -1
                minutes = minutes * -1

        # 文字列型から日時型へキャストし、エポック秒を取得
        val = (val.split('+'))[0]
        val = (val.split('-'))[0]
        val = (val.split('.'))[0]
        dt_tmp = datetime.datetime.strptime(val, '%Y/%m/%d %H:%M:%S')
        dt_tmp = dt_tmp + datetime.timedelta(hours=hours, minutes=minutes)
        dt_tmp = dt_tmp.replace(tzinfo=pytz.timezone('UTC'))

        ret_val = dt_tmp.timestamp()

        return ret_val


    def message_parse(self, pull_data):
        """
        [概要]
          取得データをパースして、インスタンスとイベント発生日時を取得
        """

        logger.logic_log('LOSI00001', 'datadog_adapter_id:%s, msg_count:%s' % (self.datadog_adapter_id, len(pull_data)))

        confirm_list = []

        evtime_list   = []
        instance_list = []

        # イベント発生日時のパース
        evtime_list_tmp = []
        match_evtime = self.datadog_adapter.match_evtime
        evtime_parse_list = match_evtime.split('.')
        result = self._parser(0, pull_data, evtime_parse_list, evtime_list_tmp)
        if not result:
            logger.system_log('LOSM38014')
            return False, []

        # イベント発生日時をエポックタイムに変換
        for et in evtime_list_tmp:
            val = self.convert_epoch_time(et)
            evtime_list.append(val)

        # インスタンスのパース
        match_instance = self.datadog_adapter.match_instance
        instance_parse_list = match_instance.split('.')
        result = self._parser(0, pull_data, instance_parse_list, instance_list)
        if not result:
            logger.system_log('LOSM38015')
            return False, []

        # インスタンスとイベント発生日時のタプルリストを生成
        if len(evtime_list) > 0 and len(evtime_list) == len(instance_list):
            confirm_list = list(zip(instance_list, evtime_list))

        return True, confirm_list


    def eventinfo_parse(self, pull_data):
        """
        [概要]
          取得データをパースして、イベント情報を取得
        """

        logger.logic_log('LOSI00001', 'datadog_adapter_id:%s, msg_count:%s' % (self.datadog_adapter_id, len(pull_data)))

        evinfo_list = []

        evinfo_tmp_list = []
        check_ev_len_list = []

        # datadog_response_key取得
        key_list = list(DatadogMatchInfo.objects.filter(datadog_adapter_id=self.datadog_adapter_id).order_by(
            'datadog_match_id').values_list('datadog_response_key', flat=True))

        # ルール条件ごとのイベント情報をパース
        for k in key_list:
            keys = k.split('.')
            tmp_list = []
            result = self._parser(0, pull_data, keys, tmp_list)
            if not result:
                logger.system_log('LOSM38016')
                return False, []

            check_ev_len_list.append(len(tmp_list))
            evinfo_tmp_list.append(tmp_list)

        # ルール条件数とパースされたイベント情報数が同一であること
        ev_len = 0
        for cel in check_ev_len_list:
            ev_len = cel
            if cel != check_ev_len_list[0]:
                return False, []

        # ルールごとのイベント情報に整列
        for i in range(ev_len):
            tmp_list = []
            for et in evinfo_tmp_list:
                tmp_list.append(et[i])

            evinfo_list.append(tmp_list)


        return True, evinfo_list


    def do_workflow(self):
        """
        [概要]
          
        """
        logger.logic_log('LOSI00001', 'None')

        datadog_adapter = None
        latest_monitoring_history = None
        now = datetime.datetime.now(pytz.timezone('UTC'))
        datadog_lastchange = None

        # 事前情報取得
        try:
            datadog_adapter = DatadogAdapter.objects.get(pk=self.datadog_adapter_id)
            self.datadog_adapter = datadog_adapter

            latest_monitoring_history = DatadogMonitoringHistory.objects.filter(
                datadog_adapter_id=self.datadog_adapter_id, status=PROCESSED
            ).order_by('datadog_lastchange').reverse().first()

        except DatadogAdapter.DoesNotExist:
            logger.logic_log('LOSM38005', self.datadog_adapter_id)
            return False

        except Exception as e:
            logger.logic_log('LOSM00001', 'Traceback: %s' % (traceback.format_exc()))
            return False

        if latest_monitoring_history != None:
            datadog_lastchange = latest_monitoring_history.datadog_lastchange
        else:
            datadog_lastchange = self.datadog_adapter.last_update_timestamp

        # 監視履歴作成 メンバ変数にセット
        try:
            self.monitoring_history = self.insert_monitoring_history(datadog_lastchange, PROCESSING)
            if self.monitoring_history is None:
                return False

        except Exception as e:
            logger.system_log('LOSM38009')
            logger.logic_log('LOSM00001', 'Traceback: %s' % (traceback.format_exc()))
            return False

        runnable = True
        error_occurred = False
        last_monitoring_time = now.strftime('%Y-%m-%dT%H:%M:%S.000Z')

        try:
            # 監視実行
            from_dt = datadog_lastchange.strftime('%Y-%m-%dT%H:%M:%S.000Z')
            from_dt = self.convert_epoch_time(from_dt)
            to_dt   = now.strftime('%Y-%m-%dT%H:%M:%S.000Z')

            result_flag, result_data, last_monitoring_time = self.execute(datadog_adapter, from_dt, to_dt)

            if not result_flag:
                error_occurred = True
                runnable = False

            # トリガー比較
            difference = []
            with transaction.atomic():
                if runnable:
                    triggerManager = ManageTrigger(self.datadog_adapter_id, self.user)

                    runnable, confirm_list = self.message_parse(result_data)
                    if not runnable:
                        raise Exception()

                    flag_array = triggerManager.main(confirm_list)

                    runnable, evinfo_list = self.eventinfo_parse(result_data)
                    if not runnable:
                        raise Exception()

                    if len(flag_array) == len(evinfo_list):
                        index = 0
                        for flg, ev in zip(flag_array, evinfo_list):
                            if flg:
                                difference.append(
                                    {
                                        'instance' : confirm_list[index][0],
                                        'evtime'   : confirm_list[index][1],
                                        'evinfo'   : ev,
                                    }
                                )

                            index = index + 1

                    if len(difference) <= 0:
                        runnable = False

                # メッセージ整形
                if runnable:
                    formatting_result, form_data = message_formatting(
                        difference, datadog_adapter.rule_type_id, self.datadog_adapter_id)

                    if not formatting_result:
                        error_occurred = True
                        runnable = False

                    if len(form_data) <= 0:
                        runnable = False

                # OASEへ本番リクエスト
                if runnable:
                    send_result = send_request(form_data)

                    if not send_result:
                        error_occurred = True
                        runnable = False

        except Exception as e:
            error_occurred = True
            logger.system_log('LOSM38010')
            logger.logic_log('LOSM00001', 'Traceback: %s' % (traceback.format_exc()))

        # 結果により監視履歴更新
        status = 'success'
        try:
            # 正常終了
            if not error_occurred:
                self.update_monitoring_history(PROCESSED, last_monitoring_time)

            # 異常終了
            else:
                status = 'error'
                self.update_monitoring_history(SERVER_ERROR, last_monitoring_time)

        except Exception as e:
            status = 'error'
            logger.system_log('LOSM38007')
            logger.logic_log('LOSM00001', 'Traceback: %s' % (traceback.format_exc()))

        logger.logic_log('LOSI00002', 'Monitoring status: %s.' % status)

        return True


if __name__ == '__main__':

    datadog_adapter_id = 0

    # 起動パラメータ
    args = sys.argv

    # 引数の共通部分設定
    if len(args) == 2:
        datadog_adapter_id = int(args[1])
    else:
        logger.system_log('LOSE38000')
        logger.logic_log('LOSE00002', 'args: %s' % (args))
        sys.exit(2)

    if ENABLE_LOAD_TEST:
        start_time = time.time()
        loadtest_logger.warn('処理開始 DatadogAdapterID[%s]' % (datadog_adapter_id))

    logger.logic_log('LOSI38001', str(datadog_adapter_id))
    try:
        datadog_sub_module = DatadogAdapterSubModules(datadog_adapter_id)

        datadog_sub_module.do_workflow()

    except Exception as e:
        logger.system_log('LOSM38010')
        logger.logic_log('LOSM00001', 'datadog_adapter_id: %s, Traceback: %s' % (str(datadog_adapter_id), traceback.format_exc()))

    if ENABLE_LOAD_TEST:
        elapsed_time = time.time() - start_time
        loadtest_logger.warn('処理終了 所要時間[%s] DatadogAdapterID[%s]' % (elapsed_time, datadog_adapter_id))

    logger.logic_log('LOSI38002', str(datadog_adapter_id))

    sys.exit(0)

