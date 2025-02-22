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

from django.db import models
from django.utils import timezone
"""
【概要】
 OASEテーブル定義
【テーブル定義】
 DOSL06002:ITAアクション履歴管理
 DOSL07001:ITAアクションマスタ
 DOSL07004:ITAパラメータ抽出条件管理
 DOSL07005:ITAパラメータ実行管理
 DOSL07006:ITAメニュー名管理
 DOSL07007:ITAドライバ権限管理
 DOSL07008:ITAメニュー項目情報
 DOSL07009:ITAドライバシステム設定
"""


class ItaActionHistory(models.Model):
    """
    DOSL06002:ITAアクション履歴管理
    """
    ita_action_his_id = models.AutoField("ITAアクション履歴ID", primary_key=True)
    action_his_id = models.IntegerField("アクション履歴ID", unique=True)
    ita_disp_name = models.CharField("ITA表示名", max_length=64)
    symphony_instance_no = models.IntegerField("Symphonyインスタンス番号", null=True)
    symphony_class_id = models.IntegerField("SymphonyクラスID", null=True)
    conductor_instance_no = models.IntegerField("Conductorインスタンス番号", null=True)
    conductor_class_id = models.IntegerField("ConductorクラスID", null=True)
    operation_id = models.IntegerField("オペレーションID", null=True)
    symphony_workflow_confirm_url = models.CharField("Symphony作業確認URL", max_length=128, null=True, blank=True)
    conductor_workflow_confirm_url = models.CharField("Conductor作業確認URL", max_length=128, null=True, blank=True)
    restapi_error_info = models.CharField("RESTAPI異常時の詳細内容", max_length=1024, null=True, blank=True)
    parameter_item_info = models.CharField("変数項目パラメータ値", max_length=1024, null=True, blank=True)
    last_update_timestamp = models.DateTimeField("最終更新日時", default=timezone.now)
    last_update_user = models.CharField("最終更新者", max_length=64)

    class Meta:
        db_table = 'OASE_T_ITA_ACTION_HISTORY'

    def __str__(self):
        return str(self.ita_action_his_id)


class ItaDriver(models.Model):
    """
    DOSL07001:ITAアクションマスタ
    """
    ita_driver_id = models.AutoField("項番", primary_key=True)
    ita_disp_name = models.CharField("ITA表示名", max_length=64, unique=True)
    version = models.CharField("バージョン", max_length=64)
    hostname = models.CharField("ホスト名", max_length=128, unique=True)
    username = models.CharField("接続ユーザ", max_length=64)
    password = models.CharField("接続パスワード", max_length=192)
    protocol = models.CharField("プロトコル", max_length=8)
    port = models.IntegerField("ポート番号")
    last_update_timestamp = models.DateTimeField("最終更新日時", default=timezone.now)
    last_update_user = models.CharField("最終更新者", max_length=64)

    class Meta:
        db_table = 'OASE_T_ITA_DRIVER'

    def __str__(self):
        return "%s(%s)" % (self.ita_disp_name, str(self.ita_driver_id))


class ItaParameterMatchInfo(models.Model):
    """
    DOSL07004:ITAパラメータ抽出条件管理
    """
    match_id = models.AutoField("パラメータ抽出条件ID", primary_key=True)
    ita_driver_id = models.IntegerField("ITAドライバID")
    menu_id = models.IntegerField("メニューID")
    parameter_name = models.CharField("パラメータ名", max_length=256)
    order = models.IntegerField("順序")
    conditional_name = models.CharField("抽出対象条件名", max_length=32)
    extraction_method1 = models.CharField("抽出方法1", max_length=512)
    extraction_method2 = models.CharField("抽出方法2", max_length=512, null=True, blank=True, default='')
    last_update_timestamp = models.DateTimeField("最終更新日時", default=timezone.now)
    last_update_user = models.CharField("最終更新者", max_length=64)

    class Meta:
        db_table = 'OASE_T_ITA_PARAMETER_MATCH_INFO'
        unique_together = (('ita_driver_id', 'menu_id', 'order'), )

    def __str__(self):
        return str(self.match_id)


class ItaParametaCommitInfo(models.Model):
    """
    DOSL07005:ITAパラメータ実行管理
    """
    commit_id = models.AutoField("パラメータ実行ID", primary_key=True)
    response_id = models.IntegerField("レスポンスID")
    commit_order = models.IntegerField("実行順序")
    menu_id = models.IntegerField("メニューID")
    ita_order = models.IntegerField("ITA順序")
    parameter_value = models.CharField("抽出パラメータ値", max_length=4000)
    last_update_timestamp = models.DateTimeField("最終更新日時", default=timezone.now)
    last_update_user = models.CharField("最終更新者", max_length=64)

    class Meta:
        db_table = 'OASE_T_ITA_PARAMETER_COMMIT_INFO'
        unique_together = (('response_id', 'commit_order', 'menu_id', 'ita_order'), )

    def __str__(self):
        return str(self.commit_id)


class ItaMenuName(models.Model):
    """
    DOSL07006:ITAメニュー名管理
    """
    ita_menu_name_id = models.AutoField("ITAメニュー名ID", primary_key=True)
    ita_driver_id = models.IntegerField("ITAドライバID")
    menu_group_id = models.IntegerField("メニューグループID")
    menu_id = models.IntegerField("メニューID")
    menu_group_name = models.CharField("メニューグループ名", max_length=64)
    menu_name = models.CharField("メニュー名", max_length=64)
    hostgroup_flag = models.IntegerField("ホストグループフラグ", default=0)
    last_update_timestamp = models.DateTimeField("最終更新日時", default=timezone.now)
    last_update_user = models.CharField("最終更新者", max_length=64)

    class Meta:
        db_table = 'OASE_T_ITA_MENU_NAME'

    def __str__(self):
        return str(self.ita_menu_name_id)


class ItaPermission(models.Model):
    """
    DOSL07007:ITAドライバ権限管理
    """
    ita_permission_id = models.AutoField("ITAドライバ権限ID", primary_key=True)
    ita_driver_id = models.IntegerField("ITAドライバID")
    group_id = models.IntegerField("グループID")
    permission_type_id = models.IntegerField("権限種別ID")
    last_update_timestamp = models.DateTimeField("最終更新日時", default=timezone.now)
    last_update_user = models.CharField("最終更新者", max_length=64)

    class Meta:
        db_table = 'OASE_T_ITA_PERMISSION'
        unique_together = (('ita_driver_id', 'group_id'), )

    def __str__(self):
        return str(self.ita_permission_id)


class ItaParameterItemInfo(models.Model):
    """
    DOSL07008:ITAメニュー項目情報
    """
    ita_parameter_item_info_id = models.AutoField("ITAメニュー項目情報ID", primary_key=True)
    ita_driver_id = models.IntegerField("ITAドライバID")
    menu_id = models.IntegerField("メニューID")
    column_group = models.CharField("カラムグループ", max_length=512)
    item_name = models.CharField("ITA項目名", max_length=256)
    item_number = models.IntegerField("項番")
    ita_order = models.IntegerField("ITA順序")
    last_update_timestamp = models.DateTimeField("最終更新日時", default=timezone.now)
    last_update_user = models.CharField("最終更新者", max_length=64)

    class Meta:
        db_table = 'OASE_T_ITA_PARAMETER_ITEM_INFO'
        unique_together = (('ita_driver_id', 'item_number'), )

    def __str__(self):
        return str(self.ita_parameter_item_info_id)


class ItaActionSystem(models.Model):
    """
    DOSL07009:ITAドライバシステム設定
    """
    item_id = models.AutoField("項番", primary_key=True)
    config_name = models.CharField("項目名", max_length=64, null=True, blank=True)
    category = models.CharField("分類", max_length=32, null=True, blank=True)
    config_id = models.CharField("識別ID", max_length=32, unique=True)
    value = models.CharField("設定値", max_length=4000, null=True, blank=True)
    maintenance_flag = models.IntegerField("メンテナンス要否フラグ", null=True)
    last_update_timestamp = models.DateTimeField("最終更新日時", default=timezone.now)
    last_update_user = models.CharField("最終更新者", max_length=64)

    class Meta:
        db_table = 'OASE_T_ITA_ACTION_SYSTEM'

    def __str__(self):
        return "%s(%s)" % (self.config_name, self.value)