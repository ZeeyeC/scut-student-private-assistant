# NaiWa角色素材来源记录

来源：[SbongeBobybl/NaiWaChatPet](https://github.com/SbongeBobybl/NaiWaChatPet)，固定提交`008eb12636f517aedecee6f1a1fc773c2f0df6c4`。选择清单见[selected-assets.json](selected-assets.json)，包含原始清单/图标/声明的SHA256及状态映射。

目前已只读检出固定提交并查看基础待机PNG；没有运行上游程序，此前没有将上游PNG放入产品；现按用户提供的许可依据选择性接入。原始待机为420×560、28帧、85ms/帧；首批惊讶三段实际为入场14帧/18fps、主体95帧/30fps、退场75帧/30fps。单帧姿态仍为单帧，手动展示保持800ms。

仓库根LICENSE为GPL-3.0，NOTICE说明DeskBox衍生部分的分发约定，并另列角色等独立资源的权利。当前检索到根声明及依赖许可证，未找到本轮角色素材的独立复用许可。2026-10-30用户明确回复“有作者授权或许可链接”，并提供本仓库链接与“项目采用GPL-3.0-only”的说明。本轮据此继续本地接入，记录为用户提供的仓库级许可依据，不将其描述为已经独立核实的角色专门许可。

选择文件的`rights.status=verified`表示该依据与固定来源已被检查、记录；`evidence_type=user-provided-repository-license`、`independent_character_license_verified=false`保留依据层级。它不是新的法律授权或版权转让认定。原始GPL全文、NOTICE与修改说明随资源包保留。未进行公开发布；今后对外分发时仍应核实声明对角色素材的适用范围。

可先使用本项目测试中生成的透明PNG验证资源工具、播放器、缓存和交互。合成QA包显式标记`qa_fixture=true`，不能混入正式包。上游动作/原图的视觉核对及当前Mac App播放验收仍需分别记录，不能以清单`reviewed`字段代替。
