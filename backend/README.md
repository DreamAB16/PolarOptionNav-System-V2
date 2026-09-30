# Backend

FastAPI HTTP application. `backend/app/routes.py` 组合 chart、environment、vessel 与 planner service facade；服务不读取前端资源。环境图层和统一环境查询使用真实外部 PolarData，规划接口仍是稳定的 mock 契约。

Run `uvicorn backend.app.main:app --reload --port 8000` from the project root.
