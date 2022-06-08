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
  Datadogアダプタメイン処理
"""


import os
import sys
import json
import subprocess
import traceback
import django
import datetime
import pytz
import fcntl
from time import sleep
from subprocess import Popen
from socket import gethostname

# OASE モジュール importパス追加
my_path       = os.path.dirname(os.path.abspath(__file__))
tmp_path      = my_path.split('oase-root')
root_dir_path = tmp_path[0] + 'oase-root'
sys.path.append(root_dir_path)

# 排他制御ファイル名
exclusive_file = tmp_path[0] + 'oase-root/temp/exclusive/datadog_monitoring.lock'

# OASE モジュール import
# #LOCAL_PATCH#
os.environ['DJANGO_SETTINGS_MODULE'] = 'confs.frameworkconfs.settings'
django.setup()

from django.conf import settings
from django.db import transaction

#################################################
# デバック用
if settings.DEBUG and getattr(settings, 'ENABLE_NOSERVICE_BACKYARDS', False):
    oase_root_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../..')
    os.environ['OASE_ROOT_DIR'] = oase_root_dir 
    os.environ['RUN_INTERVAL']  = '3'
    os.environ['PYTHON_MODULE'] = '/usr/bin/python3'
    os.environ['LOG_LEVEL']     = "TRACE"
    os.environ['LOG_DIR']       = oase_root_dir + "/logs/backyardlogs/oase_monitoring/"
#################################################

# 環境変数取得
try:
    root_dir_path = os.environ['OASE_ROOT_DIR']
    run_interval  = os.environ['RUN_INTERVAL']
    python_module = os.environ['PYTHON_MODULE']
    log_dir       = os.environ['LOG_DIR']
    log_level     = os.environ['LOG_LEVEL']
except Exception as e:
    print(str(e))
    sys.exit(2)

# ロガー初期化
from libs.commonlibs.oase_logger import OaseLogger
logger = OaseLogger.get_instance()

from web_app.models.models import User
from web_app.models.Datadog_monitoring_models import DatadogAdapter
from web_app.models.Datadog_monitoring_models import DatadogMonitoringHistory

from libs.commonlibs.common import Common
from libs.commonlibs.define import *

#-------------------
# STATUS
#-------------------
FORCE_PROCESSED = 4

DB_OASE_USER = -2140000010


class DatadogAdapterMainModules:
    """
    [クラス概要]
        Datadogアダプタメイン処理クラス
    """
    def __init__(self):
        """
        [概要]
          コンストラクタ
        """
        logger.logic_log('LOSI00001', 'None')

        self.last_update_user = User.objects.get(user_id=DB_OASE_USER).user_name
        self.hostname  = gethostname()

        logger.logic_log('LOSI00002', 'None')


    def execute_subprocess(self, aryPCB, datadog_adapter_id):
        """
        [概要]
          Datadog情報を取得する子プロセスを起動するメソッド
        """
        logger.logic_log('LOSI00001', 'aryPCB: %s, datadog_adapter_id: %s' % (aryPCB, datadog_adapter_id))

        try:
            file_path = os.path.dirname(os.path.abspath(__file__)) + '/Datadog_monitoring_sub.py'
            args = [os.environ['PYTHON_MODULE'], file_path , str(datadog_adapter_id)]

            proc = Popen(args, stderr=subprocess.PIPE, shell=False)
            aryPCB[datadog_adapter_id] = proc

        except Exception as e:
            logger.system_log('LOSM38000')
            logger.logic_log('LOSM00001', 'datadog_adapter_id: %s, Traceback: %s' % (datadog_adapter_id, traceback.format_exc()))
            return False

        logger.logic_log('LOSI00002', 'None')
        return True


    def do_normal(self, aryPCB):
        """
        Datadogアダプタ通常実行
        """
        # Datadogアダプタ設定情報を取得
        datadog_adapter_list = DatadogAdapter.objects.all()

        if len(datadog_adapter_list) > 0:
            for datadog_adapter in datadog_adapter_list:

                if datadog_adapter.status_flag > 0:
                    logger.logic_log('LOSM38023', datadog_adapter.datadog_adapter_id, datadog_adapter.status_flag)
                    continue

                # 子プロセス起動
                datadog_adapter_id = datadog_adapter.datadog_adapter_id
                ret = self.execute_subprocess(aryPCB, datadog_adapter_id)
                if ret != True:
                    return False

        return True


    def observe_subprocess(self, aryPCB):
        """
        [概要]
          子プロセス終了状況確認
        """
        logger.logic_log('LOSI00001', 'aryPCB: %s' % aryPCB)

        try:
            for datadog_adapter_id in list(aryPCB):
                if aryPCB[datadog_adapter_id].poll() != None:
                    aryPCB[datadog_adapter_id].wait()
                    aryPCB.pop(datadog_adapter_id)

        except Exception as e:
            logger.system_log('LOSM38001')
            logger.logic_log('LOSM00001', 'Traceback: %s' % (traceback.format_exc()))
            return False

        logger.logic_log('LOSI00002', 'None')
        return True


    def set_force_terminate_status(self):
        """
        [概要]
          Datadog監視履歴管理のステータスが処理中のまま
          子プロセスが終了しているレコードのステータスを
          強制処理済みに設定する。
        """

        logger.logic_log('LOSI00001', 'None')

        try:
            with transaction.atomic():

                # 監視結果管理:処理中データ取得
                datadog_monitoring_history_list = DatadogMonitoringHistory.objects.filter(
                    status = 1,
                    status_update_id = self.hostname,
                )

                for datadog_res in datadog_monitoring_history_list:
                    datadog_adapter_id = datadog_res.datadog_adapter_id

                    logger.logic_log('LOSI38003', 'OASE_T_DATADOG_MONITORING_HISTORY', datadog_adapter_id)

                    # ステータスを強制処理済みに更新
                    datadog_res.status = FORCE_PROCESSED
                    datadog_res.last_update_user = self.last_update_user
                    datadog_res.last_update_datetime = datetime.datetime.now(pytz.timezone('UTC'))
                    datadog_res.save(force_update=True)

        except Exception as e:
            logger.system_log('LOSM38017', 'OASE_T_DATADOG_MONITORING_HISTORY')
            logger.logic_log('LOSM00001', 'Traceback: %s' % (traceback.format_exc()))

        logger.logic_log('LOSI00002', 'None')


if __name__ == '__main__':

    with open(exclusive_file, "w") as f:

        # 排他ロックを獲得する。
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB )

        except IOError:
            sys.exit(0)

        aryPCB = {}
        try:
            datadog_main_module = DatadogAdapterMainModules()

            ret = datadog_main_module.do_normal(aryPCB)

            while(True):
                # 子プロセス起動状況確認
                ret = datadog_main_module.observe_subprocess(aryPCB)

                # 処理中プロセスの数を確認
                if len(aryPCB) == 0:
                    break

                # 処理中プロセスがある場合はsleep
                sleep(int(run_interval))

            datadog_main_module.set_force_terminate_status()

        except Exception as e:
            logger.system_log('LOSM38003')
            logger.logic_log('LOSM00001', 'e: %s, Traceback: %s' % (e, traceback.format_exc()))
            fcntl.flock(f, fcntl.LOCK_UN)
            sys.exit(2)

        fcntl.flock(f, fcntl.LOCK_UN)

    sys.exit(0)

