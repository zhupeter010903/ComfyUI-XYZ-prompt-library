我想要写一个comfyui的image gallery。

该gallery应该面向2000+以上的图片数量，图片大小在1024x1024以上。要求gallery运行顺滑，不会卡顿，不会每次启动comfyui或者gallery时都进行长时间的载入。可以自动随目标文件夹内容的变化而更新。gallery可以读取图片的metadata，同时也会写入新的metadata，包括favorite和tag。

gallery的入口是comfyui界面topbar的一个button。点击button会打开一个新的网页显示gallery内容。

1. 网页的主界面
1.1 主界面左侧的sidebar
1.1.1 主界面左侧sidebar的顶部是filter功能区，该功能区可以collapse，并包含以下纵向排列的component
a. 标题搜索区。“name filter:” label和一个text 输入框。filter所有图片名字包含用户输入的图片
b. 提示词搜索区。“positive prompt filter:” label和一个text输入框。图片的prompt是用“,” 分隔的一个个提示词。当用户在输入框中输入一系列逗号分隔的提示词时，filter应该返回所有在正向提示词中包含所有用户输入提示词的图片。同时，当用户在输入每一个用逗号分隔的提示词时，应该根据数据库里记录的所有图片的提示词，提供20个智能联想，并且用户可以点击这些智能联想进行auto complete
c. tag搜索区。“tag filter:” label和一个text输入框。图片的tag list是用“,” 分隔的一个个tag。当用户在输入框中输入一系列逗号分隔的tag时，filter应该返回所有在tag list中包含所有用户输入tag的图片。同时，当用户在输入每一个用逗号分隔的提示词时，应该根据数据库里记录的所有图片的tag，提供20个智能联想，并且用户可以点击这些智能联想进行auto complete
d. favorite过滤。提供一个"favorite filter:" label和一个dropdown menu，选项分别是 all/favorite/not favorite，对图片进行过滤
e. 模型过滤。提供一个"model filter:" label和一个dropdown menu，选项是all+数据库中所有图片的模型名称，过滤用选中模型生成的图片
f. 日期过滤。提供一个"date filter:" label，一个button控制是否启用filter date before，一个日历提供filter date before的日期，一个button控制是否启用filter date after，一个日历提供filter date after的日期

1.1.2 主界面左侧sidebar，在紧挨着filter功能区的下面是文件夹功能区，展示文件夹及子文件夹结构。默认读入的两个文件夹是output和input，文件夹功能区内的顶部提供两个按钮
a. 选择是否在主界面中间展示选中文件夹及其子文件夹中的所有图片，还是仅展示选中文件夹的图片
b. 点击第二个按钮会出现一个新的子界面，供用户填入新的custom文件夹路径，或者删除已有的custom文件夹路径（output和input是不可删除的）

1.2 主界面的中间
1.2.1 主界面的中间上方是一个topbar，提供以下功能
a. 滑块控制主界面一行显示多少张图片
b。dropdown manu选择alphabatic/time/size/folder name的升序或降序排序
c. 紧凑grid模式或者timeline模式切换。timeline模式下，主界面的图片会根据排序模式，被一组一组纵向分开。
d. bulk edit button。点开bulk edit模式后，可以多选图片，并出现以下新按钮：
d.1. 全部选择当前folder+filter下的图片，以及全部取消选择
d.2. 对全部选中的图片进行favorite/取消favorite
d.3. 对全部选中的图片添加/移除tag，同上，这里供用户输入tag的输入框也应该支持智能联想和auto complete
d.4. 对全部选中的图片进行移动。跳出新的子页面，供用户选择目标移动路径

1.2.2. 主界面本身
展示当前filter+folder中的图片的缩略图，所有缩略图统一大小和比例。在缩略图底部显示图片名字，在缩略图右上角提供一个favorite button，显示当前favorite状态，并且用户可以点击切换。右击图片提供移动图片和删除图片选项。左击图片进入该图片的详情页面

2. 图片详情页面
2.1 图片详情页面左侧。显示图片原图。可以放大缩小，提供两个按钮可以查看当前filter+folder+排序下的上一个/下一个图片
2.2 图片详情页右侧。显示图片的metadata，包括源自comfyui的size、创建日期、positive prompt、negative prompt、model、seed、cfg、samplet、scheduler，源自本gallery的tag、favorite，并为postive prompt,negative prompt, seed提供复制到剪切板按钮。tag和favorite两项可以编辑，且tag编辑过程中应该提供如之前描述的智能联想和auto complete。同时还要提供图片下载和图片metadata中的workflow下载两个按钮。以及返回主界面按钮和删除按钮。删除图片后也会返回主界面。


注意事项：
1. 图片的prompt是用来生成它的提示词，在comfyui生成后自动写入图片的metadata。tag是这个gallery用来给图片分类的，需要由galler添加给图片并进行维护
2. 鉴于gallery对图片根据多种不同信息检索的需求，你需要使用最能优化用户体验的算法和数据结构
3. 删除图片时需要跳出二次确认窗口
4. 移动图片时，如果目标文件夹有同名的图片，应该给被移动的图片名字后面添加后缀，并再次确认是否有同名图片，直到确认所有图片都有unique的名字，再完成移动。
5. gallery时我的xyznodes project的一部分，应该写在该文件夹内，但是和该project目前已有的nodes暂时并无关联联动。