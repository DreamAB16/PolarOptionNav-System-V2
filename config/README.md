# Config

集中管理应用设置，支持 `.env` 覆盖。数据库连接配置尚未启用，为 PostgreSQL + PostGIS 保留扩展位置。

`environment.yaml` 指向独立环境数据仓库；运行时 Provider 只通过该配置解析水深、海冰、风、流和浪的目录。不同机器可设置 `POLAR_ENVIRONMENT_DATA_ROOT` 覆盖 `environment.data_root`，无需修改代码或 Provider 接口。
