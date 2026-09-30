# Frontend

Vue 3 + TypeScript + OpenLayers 的驾驶台显示壳。OSM 是基础地图；勾选 Charts 时，前端从 chart API 获取已授权的 `coastline` GeoJSON 并通过 `MapLayerManager` 加入矢量图层。浏览器不会读取 GeoPackage 文件。

勾选 Bathymetry 时，OpenLayers 通过 XYZ 栅格接口按当前视口和缩放级别请求动态 PNG 瓦片；7GB GEBCO NetCDF 始终留在后端。

地图业务图层实现统一 `ManagedLayer` 生命周期。`App.vue` 只创建地图、注册图层并绑定 `idle/loading/ready/error` 状态；海图、水深和海冰的加载过程分别封装在独立 Layer 类中。界面文字使用中文，海冰图层根据后端环境时钟自动刷新，不提供人工日期选择。

Run `npm install` then `npm run dev`.
