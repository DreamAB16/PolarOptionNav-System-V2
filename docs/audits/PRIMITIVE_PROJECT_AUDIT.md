# Primitive Project Code-Asset Audit

只读源码审计报告。审计目标是识别旧的全域密集状态格/运动基元实现中可复用于“多尺度环境地图 → 稀疏时变航路图 → EdgeEvaluator → RG-MPAO* → CF-JRS → RCOS”的资产；不是建议恢复 50 nmi 全域高维 primitive 搜索。除本报告外，本轮未编辑项目源代码、配置、实验产物或既有报告。

## Executive finding

最值得保留的是 **3-DOF maneuvering-reference model、rate-limited turn/speed transition primitive、hashed primitive serialization、time-aware environmental edge evaluation、local hull collision checks、continuous trajectory evidence**。它们应被当作局部连接/边级可行性与验证组件，而非稀疏高层搜索状态空间。

核心限制：

- 模型参数被代码和配置标为 synthetic research parameters，不能当作 Xuelong-2 标定模型；Xuelong-2 的转弯半径、最大 yaw rate、加速度限制在 profile 中为空（`vessel/profile.py:79-90`; `config/vessels/xuelong2.yaml:19-25`）。
- 坐标约定存在跨层风险：AEQD 局部坐标说明 x/y 为 East/North；模型使用数学角 ψ（`ψ=0` 沿 +x，`ψ` 增大朝 +y）；外部方位角需要转换才能一致。`LocalMetricFrame.geo_to_local()` 当前直接把 `heading_deg` 转弧度，没有 bearing→数学角变换（`geodesy/local_frame.py:18-23,37-47`），而真实数据导航后端中可见显式 `radians(90-bearing)` 转换。需把该转换作为新接口边界合同，不要仅凭同名 `heading` 字段假设一致。
- primitive 存储的是中心参考轨迹和 maneuvering-model states/control evidence，不含 hull footprint/swept polygon；碰撞单独采用胶囊船体近似与自适应采样（`lattice/primitive.py:15-60`; `environment/collision.py:24-52,55-130`）。
- 未发现显式 Rmin、stopping-distance 或 WAIT/RETREAT primitive。现有 decelerate primitive 是有限速度模式间的推力 profile，不等同紧急停车能力。

## 1. 项目结构、入口与数据流

仓库为 `src/polar_option_nav` 的 Python package；README 将其定位为 research/scientific source of truth，并列出 RG-MPAO*、CF-JRS、RCOS、3-DOF、motion primitives、environment truth/forecast/observation/belief、real-data 和 baseline 等范围（`README.md:1-18`）。项目安装和 CLI 入口在 `pyproject.toml` 与 `src/polar_option_nav/cli/`。

主要模块：

| 模块 | 作用及相关源码 |
|---|---|
| `lattice/` | 离散化、`MotionPrimitive`、primitive generator/solver、heading/speed indexed libraries、序列化；`discretization.py`、`primitive.py`、`primitive_generator.py`、`endpoint_solver.py`、`heading_lattice.py`、`speed_lattice.py`、`primitive_serialization.py`。 |
| `vessel/` | `ShipState`/`Pose2D`/完整 6 状态、合成 3-DOF 模型、RK4 simulator、操纵输入、trim、vessel profile/geometry。 |
| `environment/` | 查询协议、时空网格/插值/批量查询、环境 views、碰撞对象/船体几何、rollout、risk cache。 |
| `polar/` | `TimeAwarePolarEdgeEvaluator` 与约束场：对 primitive/reference edge 采样、查询冰/浪/深度/海流、硬约束、track keeping、动态碰撞、风险/work 指标。 |
| `time_search/` | timed lattice graph、A*、启发函数、key；使用 heading-indexed primitive library 和 evaluator。 |
| `option_search/` | multi-policy / risk-guided label search、Pareto/archive/dominance 以及 option candidates。 |
| `paper/` | formal/diagnostic infrastructure 和可审计 baseline；`paper/baselines.py` 含 grid A*、risk-weighted A*、state-lattice A*、D* Lite、sequential alternatives。 |
| `geodesy/`, `real_data/` | WGS84/AEQD、本地 ENU 转换、真实数据 adapter/replay/navigation backend。 |
| `far_field/`, `near_field/`, `closed_loop/`, `contingent/`, `system/` | Far/Near orchestration、rolling replanning、closed-loop RCOS 类行为与 contingent policy。 |
| `artifacts/primitive_library/` | `library.json` + `library.npz` 预计算 primitive 数据。 |

典型时变 lattice 数据流：外部起点/任务 state → `LatticeDiscretizer` 得到 `(ix,iy,iheading,ispeed)` → `TimeDependentShipLatticeGraph.neighbors()` 取可用 primitive → `TimeAwarePolarEdgeEvaluator.evaluate_many()` 评价路径/环境 → 可行 transition + cost → `TimeDependentAStarPlanner` 或 `MultiPolicySearch` 扩展 labels。图在 `time_search/graph.py:29-66,84-176`；A* 在 `time_search/astar.py:47-153`；option search 依赖 timed graph 在 `option_search/search.py:60-106`。

独立 paper baseline 则直接读取冻结 Family-A grid context。`StateLatticeAStarAdapter` 从 primitive 文件加载库，并对每条 primitive transform 后逐样点查 hard mask（`paper/baselines.py:460-479,482-580`）。该 baseline 是旧全域密集 lattice 的实验入口，不是推荐的新高层架构。

CLI 入口主要在 `cli/run_option_search.py`、`run_full_mission_50nmi.py`、`run_multiscale_demo.py`、`run_contingent.py`、`run_closed_loop.py` 等。README 中列出多尺度 demo 与 50 nmi mission runner（`README.md:25-38`）。

## 2. 状态、坐标、单位

| 类型 | 字段 |
|---|---|
| `Pose2D` | `x_m`, `y_m`, `heading_rad`。 |
| `FullShipState` / simulator state array | `[x_m, y_m, heading_rad, surge_mps, sway_mps, yaw_rate_radps]`。 |
| `ShipState`（rolling planner 输入） | `lat/lon` 可空，`x/y`, `heading`, `speed`, `time`；可选 `cog/sog/stw/yaw_rate`。注释明确角度为 rad、速度 m/s、任务时钟 s（`vessel/state.py:14-36,101-133`）。 |
| lattice key | `(ix, iy, iheading, ispeed)`；时间 key 另加 time bucket（`lattice/key.py`; `time_search/key.py`）。 |

长度字段常见 m，局部 frame x/y 是 m；航速 m/s；heading rad（外部 GeoPose 用 degree）；时间 s；格距 m；真实轨迹 lat/lon 为 degree。heading 全部 normalize 到 `[0,2π)`（`vessel/state.py:8-11,101-155`）。

**坐标约定风险（必须在迁移适配器中消除）：** `LocalMetricFrame` 明示局部 x/y 为 east/north（`geodesy/local_frame.py:18-23`）。但模型位置导数是 `xdot = cos(ψ)u - sin(ψ)v`, `ydot = sin(ψ)u + cos(ψ)v`（`vessel/model_3dof.py:73-81`），碰撞胶囊主轴及 edge evaluator fallback 地速也用 `(cos ψ,sin ψ)`（`environment/collision.py:49-52`; `polar/edge_evaluator.py:1548-1582`）。因此内部 ψ=0 是 East、正向逆时针；航海 bearing=0 是 North、正向顺时针。方位→内部角应为 `ψ = (90° - bearing) mod 360°`。`real_data/navigation_backend.py:176-177` 可见该换算，而 `geodesy/local_frame.py:37-47` 对 GeoPose 直接转换单位，没有换轴。建议逐入口追踪/测试，不宜简单断言所有 real-data routes 都错，也不能把 heading 无转换传入模型。

## 3. 运动学/动力学

### Kinematic model

状态 `η=[x,y,ψ]`, body velocity `ν=[u,v,r]`。代码实现：

```text
xdot = cos(ψ) u - sin(ψ) v
ydot = sin(ψ) u + cos(ψ) v
ψdot = r
```

这是数学角定义（ψ 从 +x/East 起，逆时针为正），并不是 compass heading 下直接的 `V sin(heading), V cos(heading)`。若业务接口保证 `heading` 是 True North 顺时针，则应在适配层变为数学角 `ψ=π/2-heading`，或改用显式 NED/ENU 约定贯穿模型。否则真北方向会沿 +y，但模型 ψ=0 却沿 +x；属于坐标语义不一致风险，不是单独 cos/sin 符号 bug。

### 3-DOF dynamics

`ConfigurableThreeDOFModel` 构造对角质量矩阵：

```text
M = diag(m + X_added, m + Y_added, Izz + N_added)
M νdot = τ(control) - C(ν)ν - Dν
```

其中 `C` 在 `model_3dof.py:23-34`，`D=diag(damping_u,damping_v,damping_r)` 在 `:36-38`；推力作用于 surge，舵角产生横向力和 yaw moment。可选速度平方 rudder force 形式 `coefficient × |u|² × rudder_angle`，否则使用线性 gain（`:40-55`）。Trim 用 `thrust = damping_u × target_speed / thrust_gain`（`:57-71`）。

Simulator 使用固定步长 RK4，最后可有余步；另有逐标量 `integrate_retained_controls()`，对保存输入按原 sample times 再积分（`vessel/simulator.py:22-68,70-161`）。该模型没有海流状态/外力项，也不描述 autopilot；模型 docstring 和 rollout 文档声明它是 tactical executability reference，而非 actuator command 或控制器（`model_3dof.py:13-15`; `environment/rollout.py:19-27,43-49,77-84`）。海流影响由 edge evaluator 做 track-keeping capability correction，不平移 route geometry。

## 4. 运动基元

### 已实现种类

- **直航/cruise：** `EndpointPrimitiveSolver.solve_straight()`，优化时长以匹配目标相对 x 位移，目标航向/横向位置不作为残差（`lattice/endpoint_solver.py:155-190`）；config 默认目标为向前 11 个 lattice cells（`config/system.yaml` motion primitive section）。
- **turn：** `solve_turn()` 调整 peak rudder、hold time、recovery time，least-squares 对齐目标 x/y/heading（`lattice/endpoint_solver.py:192-265`）；舵角 rate-limited pulse 和 surge hold thrust feedback（`:71-90,337-376`）。
- **accelerate/decelerate：** `solve_speed_change()`/内部 speed-change simulation 对相邻 speed bins 生成目标速度 primitive，使用推力 rate limit 与恢复时长（`lattice/endpoint_solver.py:267-328,378-415`; library use/index in `lattice/speed_lattice.py:13-112`）。
- **WAIT/RETREAT：** 未在 primitive type/library 搜到对应实现。停止距离也没有专门算法。
- **DynamicsPrimitiveGenerator：** 另一生成器只是 rudder angles × hold-time 候选，随后等待 surge/sway/yaw rate 回到容差范围（`lattice/primitive_generator.py:16-24,27-104`）；它按 nominal speed 产生 maneuver shapes，不是完整端点连接表。

### 生成、预计算、内容

`config/system.yaml` 指定 primitive library enabled、simulation `dt=0.5s`、rudder slew `0.5 deg/s`、thrust slew `30000 N/s`、speed-hold gain、trim tolerances、endpoint solver tolerance/初值（`config/system.yaml` `motion_primitives` section）。`EndpointPrimitiveSolver` 使用 SciPy least-squares 搜索端点，再验证 position/heading/surge/sway/yaw rate、rudder/thrust slew 和 max surge（`endpoint_solver.py:417-457`）。library 的数值状态、pose、controls 和 sample_times 存在 NPZ，JSON 写各 primitive 标量、shape、hash；loader 校验整体 NPZ、每数组及 metadata hash（`primitive_serialization.py:64-182,185-266`）。

当前冻结运行库为 104 primitives：48 turns、24 cruise、16 accelerate、16 decelerate；8 heading indices、3 speed indices（3/5/7 m/s）。类型数据来自只读解析 `artifacts/primitive_library/library.json`。记录了密集样点/控制/时间，primitive duration 约 94–1886 s，样点数量从数百到数千不等。它不是任意地理环境的预计算“扫掠 primitive”，而是相对原点的局部轨迹模板，可 SE(2) transform。

每 primitive 有时间、几何长度、速度状态、舵/推力控制及端点/trim/速率诊断（`primitive.py:15-60`）；**没有环境状态、海流修正、船宽、扫掠区域或碰撞证明字段**。当前 generic hull collision 是独立胶囊形近似（length/beam/safety buffer），按中心线到圆/预测 floe tube 的 clearance 检查并对平移+转向角自适应细分（`environment/collision.py:24-52,55-130`）。

## 5. 船舶操纵模型资产

| 能力 | 当前实现 / 判断 |
|---|---|
| `Rmin` | 没有从模型计算或配置标定的最小转弯半径。profile 字段 `minimum_turning_radius_m` 存在但 Xuelong-2 值为 null。可从经验证 turn trajectories 离线测量等效半径作为诊断，不能视作 operational limit。 |
| yaw rate | 3-DOF 状态有 `r`; rudder model 通过 yaw moment 动力学形成 yaw rate；primitive endpoint 检查 terminal `r`。未设置验证 vessel-specific hard yaw-rate envelope。 |
| 加/减速 | 通过 surge equation、thrust slew-limited controls、目标 trim transitions 模拟；profile acceleration limits 为空。没有独立常数 acceleration/deceleration envelope。 |
| stopping distance | 未发现计算接口；不能从 `decelerate` segment 直接当作 emergency stopping distance。 |
| 船体几何 | `VesselGeometry` 保存 length/beam/draft/safety margin；collision `GenericSyntheticHullGeometry` 构造 capsule centerline + radius (`beam/2 + margin`)。不是多边形水线或旋转扫掠面积。 |
| swept volume | 没有预存 swept polygon。Collision functions 沿状态 samples 自适应采样，属于在线近似碰撞检测；结果精度受采样距离及插值假设约束。 |
| 海流 | 不进入 3-DOF dynamics 或 primitives；`TimeAwarePolarEdgeEvaluator` 取样 current vector，按期望地速减 current 得 required through-water vector，估算 required heading/speed、横向余量（`edge_evaluator.py:971-1045`）。route geometry 不漂移，也不解低层舵角控制。 |

可独立提取/复用：状态和物理量 schema、模型与 RK4 integrator（在明确 synthetic 标识后）、rudder/thrust rate-limited profile、endpoint matching pattern、turn/speed-change trajectory artifact、primitive integrity serialization、capsule collision sampling。不能不经校准地提取为 Xuelong-2 maneuvering envelope。

## 6. 环境查询

环境协议通过 `PlanningEnvironment.query(x,y,time)` 抽象单点查询，批量 tactical fields 另有可选协议（`environment/protocol.py:8-29`）。`synthetic_world.py` 和 `grid_planning.py` 实现批量查询/插值；`environment/views.py` 包装 truth/forecast/belief 查询边界；环境数组存储是 adapter 的实现细节。

但并非全仓都与环境解耦：

- 新/option-search tactical graph 走 `EdgeEvaluator`，环境在 constructor 注入，优先 `query_planning_fields_many`，fallback `query_many` 或单点 query；有 exact-key LRU/counters（`polar/edge_evaluator.py:129-214,1385-1471`）。这是迁移到 `EnvironmentQuery` 的首选参考。
- paper state-lattice baseline 接受专门 `GridEnvironment`，直接用 nearest cell、hard mask、边界和数组数据判定整条 primitive（`paper/baselines.py:482-555`）。这满足冻结 benchmark baseline 简单透明的需要，但绑定静态 grid/Family-A schema，不可原样作为新 edge interface。
- 旧环境 `EnvironmentGrid` 的 `cell()` nearest-index / raw arrays 访问面向 50 nmi legacy grid；不要让新搜索器直接索引其 `arrays`。通过 environment facade 或 query adapter 提供统一数据单位/插值语义。

## 7. 边评价功能盘点

`TimeAwarePolarEdgeEvaluator` 已经是现成的 EdgeEvaluator 原型：输入 current pose/timed physical state、arrival time、primitive；输出 `PolarEdgeEvaluation`，包括 feasible/reason/duration/distance、最大冰/浪、最小深度、current along track、exposure、arrival time、query count、work proxy、constraint utilization、risk tokens、track keeping/dynamic clearance（`polar/edge_evaluator.py:44-78,129-149,221-518`）。

| 功能 | 现有位置与注意点 |
|---|---|
| 空间边界 / 静态障碍 | edge evaluator 使用 `StaticTestMap`、footprint circle 做 bounds/obstacle test，按采样位置判断。 |
| 动态碰撞 | `check_hull_object_collisions`, `check_hull_tube_collisions` 用 capsule hull、same-time object/tube query、自适应采样；注意它是 capsule近似，不是多边形 sweep。 |
| depth / ice / waves | query `EnvironmentState` / batch planning fields，约束 provider 判断 hard constraints 并记录利用率与暴露；env arrays 未暴露给 search。 |
| 海流 / speed feasibility | 以 tangent 和 current 求 required through-water velocity、heading compensation、hard speed reserve/lateral clearance；仅 capability-level 评价，不重新仿真 actuator/controller。 |
| 时间传播 | primitive 的 `sample_times_s` + start arrival 形成 absolute query times；rollout 不做 endpoint snap，环境范围错误转为不可行。 |
| 风险 | 动态 risk exposure 与 `SpatioTemporalRiskToken` aggregation；option search/archive 可在 state label 上做 dominance/diversity，而 evaluator 不应拥有整个路线集语义。 |
| energy / power | `propulsion_work_model_j` 是 synthetic effort proxy，按 thrust×surge×dt 并按 required/desired speed 三次方修正；源码明确不是 requested thrust/RPM（`edge_evaluator.py:1595-1626`）。 |
| maneuverability | primitive 本身只有 model-generated trajectory and control evidence; evaluator 检查速度/环境，不代表 validated real-vessel maneuvering feasibility。 |

推荐把 evaluator 拆出协议兼容的 pure edge contract：`evaluate(edge, state, time, EnvironmentQuery, vessel capability)`；将核心约束判断、环境适配、collision, diagnostics 分层。Sparse graph edge 可以不绑定 lattice key，但可把已有 primitive 用作局部 edge witness。

## 8. 搜索算法

- `search/astar.py`：空间 lattice A*，binary heapq、g-score、parent primitive、closed set；支持以距离或时长代价与 max-speed lower-bound heuristic（`search/astar.py:24-132`）。可用于轻量单目标 lattice baseline。
- `time_search/astar.py`：以物理 endpoint state + timed key 搜索，heapq、closed node set、time heuristic；与 `TimeDependentShipLatticeGraph` 深度耦合，后者以 primitive library 产生 successor 并调用 evaluator（`time_search/graph.py:29-243`; `time_search/astar.py:47-253`）。
- `time_search/heuristic.py`：`ZeroTimeHeuristic` 与基于 goal 下界距离/max ground speed 的 admissible-style lower bound（源码 API 并未声明 proof，使用时需确认 cost assumptions）。
- `option_search/search.py` + `archive.py`：对同一离散 timed key 保留 physical/risk-aware labels，候选以 Pareto/dominance/archive 压缩，最大 label 数/目标候选受配置限制；适用于 RG-MPAO* route-option 的高级层，不应为了复用 primitive 把该搜索缩放回稠密全域 primitive graph。
- paper `StateLatticeAStarAdapter`：single-route, frozen primitive A*，cost 为 duration，heuristic distance/max ground speed；对每个原始样点 nearest grid query hard constraints（`paper/baselines.py:460-580`）。可以作为“full state-lattice baseline”。
- heapq、goal region、risk tokens、transition records 等通用概念可迁移；具体 key、closed-set/dominance 必须匹配新 sparse graph 的 identity 与 route-option semantics。

## 9. 可复用代码资产分类

| 分类 | 文件/模块 | 审计判断 |
|---|---|---|
| A | `lattice/primitive.py` | 作为局部 maneuver/reference edge schema；保留轨迹、duration、speed transition、端点误差元数据；给 heading convention 加显式 frame id。 |
| A | `environment/protocol.py`, `environment/state.py` | EnvironmentQuery / batch protocol 与环境结果 DTO 可作为 EdgeEvaluator 边界。 |
| A | `environment/collision.py` | capsule-object/tube continuous-ish collision checks 可作近场预筛/验证组件；需声明采样误差与模型假设。 |
| A | `lattice/primitive_serialization.py` | JSON+NPZ 分离、SHA256/shape/hash 校验的不可变数值资产模式值得沿用。 |
| A | `planning/goal.py`, `planning/physical_state.py`, `planning/continuity.py` | 任务 goal region、physical state、段间连续性验证概念适用于新边/航段连接。 |
| B | `vessel/state.py`, `vessel/model_3dof.py`, `vessel/simulator.py`, `vessel/control.py`, `vessel/trim.py` | 解开数学角与航海 bearing，确认时间/速度/state schema，并明确 synthetic/not calibrated 后迁移为可选局部操纵参考/oracle。 |
| B | `lattice/endpoint_solver.py`, `primitive_generator.py` | 抽出 straight/turn/speed change segment constructors 与约束检查；限定在转弯、狭窄冰道、连接、速度 transition，加入 profile capability source。 |
| B | `lattice/heading_lattice.py`, `speed_lattice.py`, `discretization.py` | 将 heading/speed indexing 拆成局部 finite maneuver connector，不用于 50 nmi 全域网格扩展。 |
| B | `polar/edge_evaluator.py`, `polar/constraint_field.py` | 复用为 EdgeEvaluator 主参考；与 lattice-specific primitive type 解耦、将目标稀疏 graph edge geometry/input protocol 化，并清楚拆 capability proxy vs physical controller. |
| B | `environment/rollout.py`, `environment/interpolation.py`, `environment/grid_planning.py`, `environment/views.py` | 复用 trajectory/time sampling 与环境插值/forecast view；统一 axis/heading/unit contract，勿让算法直接拿 arrays。 |
| C | `paper/baselines.py` 中 grid A*、risk A*、state-lattice A*、D* Lite、sequential alternatives | 保留 baseline/审稿对照与可审计实验实现，不作为主系统规划器。 State-lattice baseline 有固定 500 m、8-heading/3-speed semantics。 |
| C | `search/astar.py`, `time_search/astar.py`, `time_search/graph.py`, `time_search/heuristic.py`, lattice graph | 适合 controlled baseline 和局部图搜索 benchmark；旧全域 timed lattice 扩展非目标架构。 |
| C | `visualization/motion_primitives.py`, `visualization/option_search.py`, `cli/run_option_search.py` 与旧实验 CLI | 用于解释 primitive shapes、调试/方法对照和生成实验图；检查图上的轴约定后再用于论文。 |
| C | `tests/` 下 `vessel`, `environment`, `paper/test_family_a_and_baselines.py` 与 option/lattice相关测试 | 作为回归证据。测试存在并不等于 compass bearing/ENU 变换、真实 vessel calibration 或 full swept-hull 覆盖充分。 |
| D | 任何将 50 nmi domain 每个 500 m position × 8 headings × 3 speeds × time bins 展开为主搜索状态、并在每次扩展遍历密集 primitive points 的实现路径 | 不迁移进 sparse route graph/RG-MPAO*/CF-JRS/RCOS 主线；仅在正式定义的 baseline 中保留。 |
| D | `artifacts/primitive_library` 当作经验证 Xuelong-2 physical capability 的解释 | 不可这么用。该库依据 synthetic model/coefficient/config 产生；仅是可追溯 synthetic trajectory fixtures。 |

## 10. 不建议迁移的旧架构

不建议把 `LatticeDiscretizer(500m, 8 headings, [3,5,7]m/s)` + 每状态候选 primitive 展开 + 全域时间扩展 A* 作为新的 50 nmi planner。它将搜索复杂度直接乘上位置、航向、速度、时间维，重复遍历长 primitive sample arrays。paper baseline 中每 primitive 对样点逐个 nearest cell 查询（`paper/baselines.py:529-555`），库内单 primitive 可有数千样本；这个实现合理地可做 full lattice reference/baseline，但和“sparse time-varying route graph”主架构目标冲突。

局部 lattice/primitive 的合理范围：关键转弯处 motion connector、狭窄冰道局部 maneuver feasibility、航段 junction 连续性、速度模式切换、hull-aware local collision validation、低层导航前近场 witness validation。无需让每条开放海域 edge 都拥有完整 actuator-control rollout；可优先用解析/稀疏路径 edge evaluator，只在候选难点调用局部 oracle。

## 11. 论文用途

| 用途 | 适用性 | 使用边界 |
|---|---|---|
| full state-lattice baseline | **适用，现有实现已存在** | 将 `state_lattice_astar` 作为对照；固定库、resolution、heading/speed bins、硬约束与 start/goal semantics；报告 synthetic-model baseline，不称高保真 Xuelong-2 dynamics。 |
| Hybrid A* baseline | **当前未找到独立 Hybrid A* 实现** | 现有 `search/astar` 和 state-lattice 都是离散 lattice primitive A*；不要把它们改名为 Hybrid A*。若需要则需另行 protocol/design/implementation。 |
| 局部操纵可行性 oracle | **可作 prototype，条件性复用** | 仅在 synthetic 3-DOF model 下提供 maneuver feasibility/evidence；在 profile Rmin/yaw/accel 未知情况下不是实船 oracle。 |
| 稀疏图结果精细验证 | **最有潜力** | 将 sparse route polyline 转成局部 turns/joins，执行连续性、速率/trim、capsule collision、environment checks；报告 oracle 的近似/标定限制。 |
| 消融实验 | **适用** | 可消融 primitive-based local turn validator、speed-transition connector、swept capsule check、current track-keeping term；预先定义删除某项后 feasibility/route-set/work 指标，不将多个改变混成一个消融。 |

## 12. 迁移建议矩阵

| 旧模块 | 文件 | 当前作用 | 新系统目标模块 | 迁移方式 | 风险 | 优先级 |
|---|---|---|---|---|---|---|
| 状态/姿态 | `vessel/state.py` | pose 与 3/6 DOF state DTO | `EdgeEvaluator`, local oracle | 固定并显式命名 `ENU + mathematical yaw` 或 `ENU + compass bearing`，用不同类型/转换函数 | 同一 `heading_rad` 混合两种零向/正向 | P0 |
| 地理 frame | `geodesy/local_frame.py`, `geodesy/types.py` | AEQD ENU 与 bearing DTO | environment/route adapters | 单测 East/North axis、真北 bearing、round-trip；纠正/隔离直接 rad conversion | 当前 GeoPose 转换无显式 bearing-map | P0 |
| vessel dynamics | `vessel/model_3dof.py`, `parameters.py`, `simulator.py` | 合成 3DOF maneuver reference | local maneuver oracle | 保留为 synthetic plugin；分离参数来源与 validated real vessel profile | 未标定、无环境载荷/海流动力学 | P1 |
| primitive schema | `lattice/primitive.py` | dense relative trajectory + time + controls evidence | sparse graph local connector | 新增显式 frame/footprint metadata 或单独 envelope object；高层 graph edge只引用证据 | 当前 control 容易被误读为执行命令 | P1 |
| endpoint solve | `lattice/endpoint_solver.py` | least-squares turn/straight/speed transition solve | critical-edge local connector | 只对局部 keypoints/junction 调用；限制候选数/缓存 immutable output | 优化器初值敏感、当前 synthetic parameters | P1 |
| generator | `lattice/primitive_generator.py` | rudder-hold/recovery maneuvers | offline local maneuver library | 用于 fixture/候选生成，加入 explicit scope/metadata | nominal-speed-only shape | P2 |
| primitive library | `artifacts/primitive_library/library.json`, `.npz`; loader | 104 条已哈希轨迹资产 | local connector registry/test corpus | 校验 hash，按 model/config/frame version 分离；不可 silent regenerate | 参数/heading semantics 变更即不兼容 | P1 |
| environment query | `environment/protocol.py`, `grid_planning.py`, `views.py` | scalar/batched spatiotemporal queries | multi-scale EnvironmentQuery | 保留 protocol；统一 x/y axes、time interpolation、forecast/observation contract | legacy `EnvironmentGrid` 有 direct layers | P1 |
| edge evaluator | `polar/edge_evaluator.py`, `constraint_field.py` | environmental, current, risk, collision feasibility/counters | 新 EdgeEvaluator | 抽取 interface/result contract；支持 polyline graph edges + optional maneuver witnesses | 和 `MotionPrimitive`, `StaticTestMap`, synthetic capability 耦合 | P0 |
| hull checks | `environment/collision.py`, `vessel/geometry.py` | capsule/object/floe collision | local swept-area validation | 保留 capsule broad/narrow phase；后续替换/补充 polygon sweep 及 conservative bounds | capsule 不表达艏艉/非凸形状 | P1 |
| timed lattice graph | `time_search/graph.py`, `time_search/key.py` | time-bin keyed primitive graph successors | baseline/local tactical subgraph | 留作 state-lattice baseline/局部搜索；新主图独立节点 key | 继承全域高维扩展 | P2 |
| A* / heuristic | `time_search/astar.py`, `search/astar.py`, `time_search/heuristic.py` | single route search | local connector/baseline | 复用 heap/A* 概念； heuristic 要按新 edge cost 重证 | heuristic admissibility 假设需验证 | P2 |
| option labels/archive | `option_search/search.py`, `archive.py`, `dominance.py` | multi-route labels/dominance | RG-MPAO* | 保留其上层风险 Pareto / route option semantics，不把 primitive全域化 | 状态等价与新 sparse graph identity 需统一 | P1 |
| paper baselines | `paper/baselines.py` | baseline adapters/metrics/evidence | manuscript experiments | 作为对照实验隔离包；保持严格 run contract | baseline语义不能混当主算法 | P1 |
| visualization/tests | `visualization/motion_primitives.py`, `tests/**` | diagnostic rendering/regression | local connector QA | 移植 focused tests；补 ENU-bearing、swept bounds 与 no-drift/current semantics | 当前 coverage 不代表物理真实性 | P2 |

## 13. 测试与未验证项

只读检查了测试目录与测试源码名称；本轮未运行 pytest 或 planner。相关测试分布包括 `tests/vessel/test_vessel_profile.py`、`tests/environment/test_grid_time_interpolation.py`、`tests/paper/test_family_a_and_baselines.py`，另有 architecture/navigation/planning tests。profile 测试确认 turning radius 未提供，并不验证真实 maneuver envelope。

迁移前应新增/确认以下 focused checks：

1. ENU cardinal-direction tests：数学 yaw 0→East、π/2→North；compass bearing 0→North、90→East；两类转换 round-trip。
2. 对 `LocalMetricFrame.geo_to_local(GeoPose)` 的 heading contract test，确保投影坐标 frame 与角度 frame 不被混淆。
3. primitive junction 的 pose + surge/sway/yaw-rate + time continuity tests，含 wrapped heading edge cases。
4. capsule swept clearance 在长边、急转、近距离动态障碍处的采样收敛测试；若目标承诺 conservative collision，要证明采样间隙不会漏检或显式降低 claim。
5. edge evaluator 对环境越界、hard depth/ice/wave、current head/cross-track、uncertain forecast、query batching/cache 与 reason code 的单测。
6. physical profile unknown 的 fail-closed/diagnostic policy：Rmin、yaw/acceleration limits 未知时，不把 synthetic profile 产物报告为实船可行性。

## 审计结论

该旧项目可提供高价值的**局部操纵轨迹、时间传播、环境边评价、动态碰撞和证据完整性资产**。建议把 `TimeAwarePolarEdgeEvaluator` 作为新 EdgeEvaluator 的主要代码参考，把 `MotionPrimitive`/endpoint solver 降级为按需的局部连接或验证器，把 state-lattice A* 限定为 baseline。最先要消除的是数学 yaw 与航海 bearing 的边界歧义；其次是明确 synthetic vessel model 对真实船舶 capability 的限制。不得把 500 m × 8 heading × 3 speed × time lattice 重新引入 50 nmi 主搜索器。
