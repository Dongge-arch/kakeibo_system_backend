# Armbian 自動連携バッチ

Amazon / Belc など Lambda からアクセスしにくい連携を、Armbian サーバー上の batch として実行します。

## 仕組み

- 実行入口: `python -m src.batch.auto_input_scheduler.server_runner`
- 対象: `BELC,ETC,AMAZON`
- 認証情報: クラウドDBの `kakeibo.auto_input_info` から取得
- 保存先: 既存 batch と同じクラウドDB
- 定期実行: systemd timer で毎日 `00:00`

## 配置

Windows 側から実行します。

```powershell
.\deploy\armbian\deploy_armbian_batch.ps1 -HostAlias pi -RemoteDir /opt/home-kakeibo-batch
```

初回だけ Armbian 側の `/etc/home-kakeibo-batch.env` にクラウドDB接続情報を設定してください。

## 手動実行

```bash
cd /opt/home-kakeibo-batch
.venv/bin/python -m src.batch.auto_input_scheduler.server_runner --connection-types BELC,ETC,AMAZON
```

## 今後の拡張

現在は毎日 `00:00` 固定です。曜日、日付、時刻指定は `home-kakeibo-auto-input.timer` の `OnCalendar` を増やすか、DBにスケジュール設定を持たせて `server_runner.py` に条件判定を追加します。
