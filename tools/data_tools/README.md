# PolarOptionNav Data Tools

`tools/data_tools` 是独立的离线数据工具，负责环境数据下载、NetCDF 检查和压缩预处理。应用运行时不会导入本目录；删除整个目录不影响前端、后端、环境服务或规划器启动。

环境二进制数据默认写入 `config/environment.yaml` 所指的外部 PolarData 仓库。可为任一下载器传入 `--data-root G:/gpy_NO_DELETE!/PolarData` 覆盖该默认值；账号、密码和令牌绝不写入项目或数据仓库。

## 目录

```text
tools/data_tools/
├── download/
│   ├── download_copernicus_ice.py
│   ├── download_copernicus_current.py
│   ├── download_copernicus_wave.py
│   └── download_wind_era5.py
├── inspect/
│   ├── inspect_nc.py
│   ├── inspect_current.py
│   ├── inspect_wave.py
│   └── check_dataset.py
├── preprocess/
│   ├── preprocess_copernicus_ice.py
│   └── preprocess_bathymetry_polar.py
├── tests/
├── requirements.txt
└── README.md
```

## 独立安装

在项目根目录执行：

```powershell
py -m venv tools/data_tools/.venv
tools/data_tools/.venv/Scripts/Activate.ps1
python -m pip install -r tools/data_tools/requirements.txt
```

## 下载 Copernicus Marine 海冰

下载器使用产品 `ARCTIC_ANALYSISFORECAST_PHY_ICE_002_011` 的小时级数据集 `cmems_mod_arc_phy_anfc_nextsim_hm`，请求 `siconc`、`sithick`、`siconc_my`、`siconc_young`、`vxsi`、`vysi` 和 `sisnthick`。

凭据不得写入项目。首次使用可执行：

```powershell
copernicusmarine login
```

也可以只在当前终端设置 `COPERNICUSMARINE_SERVICE_USERNAME` 和 `COPERNICUSMARINE_SERVICE_PASSWORD`。脚本不会接收、打印或保存密码。

无网络预览：

```powershell
python -m tools.data_tools.download.download_copernicus_ice --date 2025-02-15 --dry-run
```

下载单日 12:00 UTC 数据：

```powershell
python -m tools.data_tools.download.download_copernicus_ice --date 2025-02-15
```

下载逐日序列：

```powershell
python -m tools.data_tools.download.download_copernicus_ice --start 2025-02-15 --end 2025-02-20
```

原始文件默认保存到配置的 `ice/raw/copernicus/arctic_ice_YYYYMMDD.nc`。已有文件会先验证 CF 元数据后跳过，网络错误使用指数退避重试，进度由 Copernicus Marine Toolbox 输出。

## 检查 NetCDF

```powershell
python -m tools.data_tools.inspect.inspect_nc data/environment/ice/raw/copernicus/arctic_ice_20250215.nc --dataset-type ice
```

检查器报告文件格式、维度、变量、单位、坐标/时间范围和数值范围。大变量默认只采样有限窗口；需要精确统计时使用 `--full-stats`。

## 下载与检查北极表层海流

以下命令下载与海冰实验日期一致的TOPAZ5去潮表层海流原始投影网格，只包含`vxo/vyo`：

```powershell
python -m tools.data_tools.download.download_copernicus_current --all
python -m tools.data_tools.inspect.inspect_current data/environment/current/raw/Copernicus_current_20250215.nc data/environment/current/raw/Copernicus_current_20250815.nc
```

下载器明确选择`originalGrid`。其中`vxo/vyo`是TOPAZ北极极射网格x/y方向分量，不是可直接当作地理east/north使用的分量。

通用入口支持 `ice`、`wind`、`current`、`wave` 和 `bathymetry`：

```powershell
python -m tools.data_tools.inspect.check_dataset ice data/environment/ice/raw/copernicus/arctic_ice_20250215.nc
```

## 压缩预处理

```powershell
python -m tools.data_tools.preprocess.preprocess_copernicus_ice data/environment/ice/raw/copernicus/arctic_ice_20250215.nc
```

默认输出到配置的 `ice/processed/copernicus/arctic_ice_YYYYMMDD.nc`。工具保留七个业务变量及 `time`、`latitude`、`longitude` 坐标，不改变物理量或规则经纬网，只进行 NetCDF4 zlib/shuffle 压缩和分块复制，避免整文件载入内存。

指定输出或压缩级别：

```powershell
python -m tools.data_tools.preprocess.preprocess_copernicus_ice input.nc --output output.nc --compression-level 4
```

## 北极水深投影预处理

全球 GEBCO 仍由应用动态生成 EPSG:3857 瓦片。北极战略与极地详细视图使用独立的 EPSG:3413 网格，避免 Web Mercator 在 85.0511°N 的截断：

```powershell
python -m tools.data_tools.preprocess.preprocess_bathymetry_polar
```

默认产物为配置的 `bathymetry/processed/bathymetry_polar_3413.tif`。它覆盖 30°N--90°N，在 EPSG:3413 中以 1,000 米规则网格保存；GeoTIFF NoData 为 `-32768`，而非零深度。可按存储或显示精度调整：

```powershell
python -m tools.data_tools.preprocess.preprocess_bathymetry_polar --resolution-metres 500
```

## 数据目录规范

- `ice/raw/copernicus/`：未经修改的下载文件。
- `ice/processed/copernicus/`：供 `CopernicusIceProvider` 使用的压缩成品。
- `current/raw/`：Copernicus Marine TOPAZ5原始投影网格海流。
- `current/processed/`：为后续CurrentProvider预留，本阶段为空。
- 临时写入使用 `.tmp.nc`，成功后原子替换为目标文件；失败时自动清理临时文件。

## 扩展其他数据源

新数据源应新增独立下载器和预处理器，不把远端地址或文件路径写入应用运行时。NetCDF 数据可复用 `inspect_nc()`；测试使用小型合成文件，不连接真实网络。

## 测试

```powershell
python -m pytest tools/data_tools/tests -q
```

## ERA5 风场兼容工具

当前默认运行时风场为外部 PolarData 仓库中的 CARRA2 月度配对文件。以下 ERA5 工具仅为兼容后备，不用于默认 CARRA2Provider：

先在用户目录配置 `.cdsapirc`，再只下载与海冰样本一致的 15 日小时数据：

```powershell
python -m tools.data_tools.download.download_wind_era5 --month 202502 --days 15
python -m tools.data_tools.download.download_wind_era5 --month 202508 --days 15
```

无网络预览请求范围：

```powershell
python -m tools.data_tools.download.download_wind_era5 --month 202502 --days 15 --dry-run
```

## 15 天东北航道环境窗口

下载器使用本机 CDS / Copernicus Marine 认证配置，绝不读取或保存账号、密码或令牌。为保持现有运行时 Provider 的按日期索引，TOPAZ 海流、WAM 海浪和 neXtSIM 海冰保留为每日文件；CARRA2 风场使用外部月度配对文件。下载已存在且校验正确的日期会跳过。

```powershell
$days = '8,9,10,11,12,13,14,15,16,17,18,19,20,21,22'
python -m tools.data_tools.download.download_copernicus_current --start 2025-02-08 --end 2025-02-22
python -m tools.data_tools.download.download_copernicus_current --start 2025-08-08 --end 2025-08-22
python -m tools.data_tools.download.download_copernicus_wave --start 2025-02-08 --end 2025-02-22
python -m tools.data_tools.download.download_copernicus_wave --start 2025-08-08 --end 2025-08-22
python -m tools.data_tools.download.download_copernicus_ice --start 2025-02-08 --end 2025-02-22
python -m tools.data_tools.download.download_copernicus_ice --start 2025-08-08 --end 2025-08-22
```

下载完成后可使用 `inspect_navigation_window` 生成可复核 JSON 报告（包含文件大小、时间范围、变量、空间坐标、有效/NoData 比例和 SHA256）。注意：该脚本的风场规则仍针对 ERA5 `u10/v10` 文件；当前 CARRA2 风场应以 Provider 元数据和 CARRA2 专用检查流程核对，不能将此报告当作 CARRA2 完整性结论。

```powershell
python -m tools.data_tools.inspect.inspect_navigation_window `
  --start 2025-02-08T00:00:00+00:00 --end 2025-02-22T23:00:00+00:00 `
  --output data/environment/reports/navigation_window_20250208_20250222.json
```
