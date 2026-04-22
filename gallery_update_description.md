gallery的初始版本全部更新完毕后的update意见，在明确告知前，忽视以下内容

1. folder tree里的folder可折叠，可以右击folder进行改名、移动、删除、创建子文件夹、在本地操作系统文件夹中打开（这一项是非必要的可选功能，取决于实现难易度）
2. 增加 light mode/dark mode开关
3. filter增加“all/有comfyui meta data/没有comfyui meta data”项
4. filter prompt增加match prompt/match word/match string选项，match prompt mode下，比如用户输入"masterpiece, blonde"，就只会匹配positive prompt里正好有“masterpiece” 和 “blonde”这两个prompt的图片。match word mode下，还会额外匹配positive prompt的“blonde hair”，“masterpiece illustration”等prompt，因为match的是空格分隔的单词。 match string mode模式下，还会额外匹配positive prompt里的"blondehair" 这种单词。同时match prompt模式下应该自动联想 prompt，match word模式下应该自动联想word，match string模式下则不用提供自动联想
5. sql数据库中，应该把所有下划线"_"都normalize为空格
6. 图像缩略图grid界面里，多选模式下，支持像windows操作系统一样的通过鼠标拖拽和shift进行批量选择或取消选择
7. 图像缩略图grid界面，应该支持通过拖拽单个缩略图（或者多选模式下的全部选中缩略图）到左侧sidebar的folder，进行移动
8. 右击缩略图应该支持改名、移动、删除。
9. 多选模式下，应该可以通过topbar进行集体移动、删除、统一增减tag、统一favorite/unfavorite
10. detail模式下，应该支持修改图片名称、tag、favorite状态
11. 目前output folder下有一个_thumbs subfolder，并且里面的图片出现在gallery系统中，这是完全不应该的，thumbnail文件应该储存在别的地方，比如xyznode folder里。如果这些不是本gallery使用的thumbnail，则直接删除
12. 在detail view里，positive prompt添加选项，选择展示原本的positive prompt，还是经过数据库normalize的prompt
13. 数据库处理prompt时，移除PROJECT_SPEC.md的这一条"Strip leftover grouping punctuation — (), [], {}, \."，如果一个prompt是"yd \(orange maru\)"那么就应该原样保留进入数据库。

final. 作为图片gallery，视觉效果非常重要，对整个gallery的design进行美化。比如目前设计中，黑色背景的gallery下，几个滚动条都是白底+灰色条，显得又简陋又突兀。
