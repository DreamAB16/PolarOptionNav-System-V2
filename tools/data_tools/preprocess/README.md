# Preprocess

该目录包含独立的离线预处理工具，不被前端、后端、服务或规划器导入。

`preprocess_copernicus_ice.py` 读取 Copernicus Marine neXtSIM-F 原始 NetCDF，保留：

- `siconc`
- `sithick`
- `siconc_my`
- `siconc_young`
- `vxsi`
- `vysi`
- `sisnthick`
- `time`、`latitude`、`longitude`

它保持原始规则经纬网和变量物理意义，按行分块复制，并使用 NetCDF4 zlib、shuffle 和默认 `complevel=4` 压缩：

```powershell
python -m tools.data_tools.preprocess.preprocess_copernicus_ice data/environment/ice/raw/copernicus/arctic_ice_20250215.nc
```

默认输出为 `data/environment/ice/processed/copernicus/arctic_ice_YYYYMMDD.nc`。`raw/copernicus` 保存原始下载文件，`processed/copernicus` 保存可重新生成的服务输入文件。
