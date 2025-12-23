模型下载默认存放地址#
无论是使用命令行还是ModelScope SDK，模型会下载到~/.cache/modelscope/hub默认路径下。如果需要修改 cache 目录，可以手动设置环境变量：MODELSCOPE_CACHE，完成设置后，模型将下载到该环境变量指定的目录中。


使用命令行工具下载#
modelscope download --help

    usage: modelscope <command> [<args>] download [-h] --model MODEL [--revision REVISION] [--cache_dir CACHE_DIR] [--local_dir LOCAL_DIR] [--include [INCLUDE ...]] [--exclude [EXCLUDE ...]] [files ...]
    
    positional arguments:
      files                 Specify relative path to the repository file(s) to download.(e.g 'tokenizer.json', 'onnx/decoder_model.onnx').
    
    options:
      -h, --help            show this help message and exit
      --model MODEL         The model id to be downloaded.
      --revision REVISION   Revision of the model.
      --cache_dir CACHE_DIR
                            Cache directory to save model.
      --local_dir LOCAL_DIR
                            File will be downloaded to local location specified bylocal_dir, in this case, cache_dir parameter will be ignored.
      --include [INCLUDE ...]
                            Glob patterns to match files to download.Ignored if file is specified
      --exclude [EXCLUDE ...]
                            Glob patterns to exclude from files to download.Ignored if file is specified
使用示例#
命令示例（以Qwen2-7B）模型为例

下载整个模型repo（到默认cache地址）#
    modelscope download --model 'Qwen/Qwen2-7b' 
下载整个模型repo到指定目录#
    modelscope download --model 'Qwen/Qwen2-7b' --local_dir 'path/to/dir'
指定下载单个文件(以'tokenizer.json'文件为例)#
    modelscope download --model 'Qwen/Qwen2-7b' tokenizer.json
指定下载多个个文件#
    modelscope download --model 'Qwen/Qwen2-7b' tokenizer.json config.json
指定下载某些文件#
    modelscope download --model 'Qwen/Qwen2-7b' --include '*.safetensors'
过滤指定文件#
    modelscope download --model 'Qwen/Qwen2-7b' --exclude '*.safetensors'
指定下载cache_dir#
    modelscope download --model 'Qwen/Qwen2-7b' --include '*.json' --cache_dir './cache_dir'
模型文件将被下载到'cache_dir/Qwen/Qwen2-7b'。

指定下载local_dir#
    modelscope download --model 'Qwen/Qwen2-7b' --include '*.json' --local_dir './local_dir'
模型文件将被下载到'./local_dir'。

如果cache_dir和local_dir参数同时被指定，local_dir优先级高，cache_dir将被忽略。



我们推荐使用命令行或者 ModelScope SDK 来进行模型的下载。操作指引
在下载前，请先通过如下命令安装ModelScope

pip install modelscope
命令行下载
下载完整模型库

modelscope download --model AI-ModelScope/bge-large-zh-v1.5
下载单个文件到指定本地文件夹（以下载README.md到当前路径下“dir”目录为例）

modelscope download --model AI-ModelScope/bge-large-zh-v1.5 README.md --local_dir ./dir
更多更丰富的命令行下载选项，可参见具体文档
SDK下载
#模型下载
from modelscope import snapshot_download
model_dir = snapshot_download('AI-ModelScope/bge-large-zh-v1.5')
Git下载
请确保 lfs 已经被正确安装

git lfs install
git clone https://www.modelscope.cn/AI-ModelScope/bge-large-zh-v1.5.git
如果您希望跳过 lfs 大文件下载，可以使用如下命令

GIT_LFS_SKIP_SMUDGE=1 git clone https://www.modelscope.cn/AI-Mod