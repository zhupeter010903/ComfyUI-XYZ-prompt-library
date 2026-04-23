gallery的初始版本全部更新完毕后的update意见，在明确告知前，忽视以下内容

1. folder tree里的folder可折叠，可以右击folder进行改名、移动、删除、创建子文件夹、在本地操作系统文件夹中打开（这一项是非必要的可选功能，取决于实现难易度）
2. 增加 light mode/dark mode开关
3. filter增加“all/有comfyui meta data/没有comfyui meta data”项
4. filter prompt分为match prompt/match word/match string三个单独的filter，match prompt filter下，比如用户输入"masterpiece, blonde"，就只会匹配positive prompt里正好有“masterpiece” 和 “blonde”这两个prompt的图片。match word filter下，还会额外匹配positive prompt的“blonde hair”，“masterpiece illustration”等prompt，因为match的是空格分隔的单词。 match string filter下，还会额外匹配positive prompt里的"blondehair" 这种单词。同时match prompt下应该自动联想 prompt，match word下应该自动联想word，match string下则不用提供自动联想
5. sql数据库中，应该把所有下划线"_"都normalize为空格
6. 图像缩略图grid界面里，多选模式下，支持像windows操作系统一样的通过鼠标拖拽和shift进行批量选择或取消选择
7. 图像缩略图grid界面，应该支持通过拖拽单个缩略图（或者多选模式下的全部选中缩略图）到左侧sidebar的folder，进行移动
8. 右击缩略图应该支持改名、移动、删除。
9. 多选模式下，应该可以通过topbar进行集体移动、删除、统一增减tag、统一favorite/unfavorite
10. detail模式下，应该支持修改图片名称、tag、favorite状态
11. 目前output folder下有一个_thumbs subfolder，并且里面的图片出现在gallery系统中，这是完全不应该的，thumbnail文件应该储存在别的地方，比如xyznode folder里。如果这些不是本gallery使用的thumbnail，则直接删除
12. 在detail view里，positive prompt添加选项，选择展示原本的positive prompt，还是经过数据库normalize的prompt
13. 数据库处理prompt时，移除PROJECT_SPEC.md的这一条"Strip leftover grouping punctuation — (), [], {}, \."，如果一个prompt是"yd \(orange maru\)"那么就应该原样保留进入数据库。
14. 在detail view的右边，把gallery相关的metadata放在最上面
15. topbar里增加一个setting开关。setting button打开一个子页面，页面内根据功能分成不同区，可以通过子页面的topbar跳转到不同区。setting 页面功能如下：
- 在setting页面可以开启/关闭开发者模式。在非开发者模式，隐藏所有普通用户不需要知道的/无法直接理解的信息，比如bulk edit的mode显示，和数据库有关的id等。
- 在setting里可以设置下载图片的规则：下载带有全部metadata的图片/下载不包含workflow的图片/下载完全的clean copy。下载规则对bulk selection/右击缩略图/detail view里的下载功能统一生效
- 可以在setting里自定义下载路径。
- filter setting：对于每一项filter功能，在setting页面提供一个checkbox，只有选中对应的checkbox，才会在main view的filter区显示该filter选项
- tag management：可以搜索、删除tag，可以一键清除usage数量为0的tag，可以对tag进行重命名并自动普及到所有拥有该tag的图片。
- custom image folder path：setting里可以添加自定义的image folder路径，或者对现有的custom image folder进行manage和删除，但是output和input两个folder是不能改动的。
18. 在右击缩略图、detail view、bulk selection中，实现下载图片功能。

final. 作为图片gallery，视觉效果非常重要，对整个gallery的desing进行美化。优化整个gallery的color design、visual design、font design、component layout。整体风格学习apple的photo album。比如目前设计中，黑色背景的gallery下，几个滚动条都是白底+灰色条，显得又简陋又突兀。

