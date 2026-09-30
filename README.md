# PolarOptionNav-System-V2

极地船舶环境感知与数据融合平台。系统为驾驶台提供环境态势和船舶参数信息，最终执行权属于船长；本项目当前不实现自动驾驶或航线规划算法。

## 当前范围

- Vue 3 + TypeScript + OpenLayers 地图壳
- FastAPI 状态、海图、环境和安全查询 API
- `core` 中的环境、船舶和未来 Planner 接口数据契约
- 可替换的数据 provider 和服务边界
- GeoPackage 海岸线、GEBCO 水深栅格、Copernicus neXtSIM-F 海冰瓦片显示
- CARRA2 风场、TOPAZ5 海流、Arctic WAM 海浪的时间感知查询和地图矢量显示
- `EnvironmentTimeManager` 时间轴播放，以及统一的 `EnvironmentQueryService` 和 `EnvironmentGrid` 点/批量查询
- Draft + UKC 安全水深判断框架
- 启动、API 连通和前端构建测试

Planner 只保留稳定的服务边界；RG-MPAO*、CF-JRS、RCOS、船舶动力学和航线风险计算留待后续接入。

## 目录

详见 [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md)。

## 快速启动

后端（PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

前端（另一个终端）：

```powershell
cd frontend
npm install
npm run dev
```

打开 <http://localhost:5173>。API 文档位于 <http://localhost:8000/docs>。
