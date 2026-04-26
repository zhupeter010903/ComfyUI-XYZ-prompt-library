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


v1.1.1
1. sidebar中，给folder treesection增加自己的scroll bar目的是上下scroll folder tree时，上方的filter section始终处于原位置。
2. 在detailview里可以用left arrow key和right arrow key切换previous/next image。当鼠标放在左侧的image view里时，上下滚动鼠标滚轮应该可以控制图片放大缩小。
3. phrase、word、taag的auto complete目前只会识别用户属于作为match对象的开头的情况。比如用户输入blonde会在auto complete里match"blonde eyes"，但是用户输入eyes则不会。在setting里增加一个开关，切换是只作为联想对象的开头提供auto complete，还是可以作为联想对象的任意substring。
4. side bar和main view，以及filter section和folder section都有draggable handler可以调整layout。在setting里增加一个按钮可以一键把layout恢复到default

v1.2
1. 遍历全部ui，作为专业的software engineering用户交互界面设计师，优化ui的美观性和可读性，面向普通comfyui用户。
1.1 detailview界面的scroll bar和输入框是白色底的，在darkmode下和整体颜色冲突很突兀。应该遵守main view下输入框和scroll bar的设计
1.2 folder tree应该适当进行设计或使用icon，让用户第一眼看过去就能根据经验和尝试知道这是文件夹系统
1.3 对所有ui，icon的风格设计进行统一化和优化。比如现在各个位置的返回按钮就是一个蓝色的“← Back”，略显简陋
1.4 如果一个ui的功能较为复杂，不够直觉性，光凭名称可能产生误会，则可以在旁边添加一个?，把鼠标移到问号上时会在浮窗显示细节解释。
1.5 现在各处ui还残留一些开发时期的印记，比如name filter的输入框里默认显示"substring (debounced 250ms)"，很明显对普通用户来说是丑陋和莫名其妙的
整体设计应该遵守以下要求：
a. 模仿apple苹果在ios系统和macos系统里的照片系统的设计风格
b. 保持整个gallery的设计统一，包括main view，detail view，setting
c. 用户友好的ui视觉设计以及指引
d. 没有过于简陋的ui设计

2. 遍历整个gallery implementation，检查以下要求是否达到：
2.1 当os系统里的图片和文件夹发生任何变化时，都会立即反映到gallery的后端和前端
2.2 gallery的前端视图不会在任何操作中频繁闪烁（可能源自后台导致的频繁刷新更新，或其他原因）

3. 涉及2.2，对于任何涉及>1张图片的处理，包括bulk selection下的任何操作、对folder操作时导致的对多个图片的操作、在setting里增删custom image folder，在setting里edit或删除tag、或者任何你在遍历gallery代码中发现的batch operation。在进行这些操作的后端、数据库、前端更新时，跳出一个progress bar窗口，展示处理进度，并在progress bar下面展示以下信息：处理对象、处理操作、处理结果。在处理结束后自动关闭该窗口。

4. grid view增加切换compact view和line view的按钮，compact view就是目前的模式。line view应该是以下这种设计
-output-------------------------------
img1 img2 img3 img4 img5 img6
img7

-output/test-------------------------------
img1 img2 img3 img4 img5 img6
img7

-input--------------------------------
img1 img2 img3 img4 img5 img6
img7

其中每个section的header，取决于sort method，
- sort by time时，每个section的header是日期（年月日，不包含小时分钟秒）
- sort by alphabet时，header是首字母
- sort by size时，header是1000kb~800kb这种bin
- sort by folder时，就是各个folder的相对路径。比如output下面的subfolder test，就应该显示output/test，比如有一个custom image folder “download”，下面有一个subfolder “test2”，就应该分别显示“download”和“download/test2”。且每个folder的header下不会recursive展示子文件夹内的image。这里也更正一下，sort by folder的算法是应该按照上述这种相对路径排序，而不是只根据folder的name排序。
