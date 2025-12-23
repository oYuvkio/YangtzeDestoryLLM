对于服务提供的主要操作：

- HTTP请求方法为POST。
- 请求体和响应体均为JSON数据（JSON对象）。
- 当请求处理成功时，响应状态码为`200`，响应体的属性如下：

| 名称        | 类型      | 含义                          |
| :---------- | :-------- | :---------------------------- |
| `logId`     | `string`  | 请求的UUID。                  |
| `errorCode` | `integer` | 错误码。固定为`0`。           |
| `errorMsg`  | `string`  | 错误说明。固定为`"Success"`。 |
| `result`    | `object`  | 操作结果。                    |

- 当请求处理未成功时，响应体的属性如下：

| 名称        | 类型      | 含义                       |
| :---------- | :-------- | :------------------------- |
| `logId`     | `string`  | 请求的UUID。               |
| `errorCode` | `integer` | 错误码。与响应状态码相同。 |
| `errorMsg`  | `string`  | 错误说明。                 |

服务提供的主要操作如下：

- **`infer`**

进行版面解析。

```
POST /layout-parsing
```

- 请求体的属性如下：

| 名称                        | 类型                                   | 含义                                                         | 是否必填 |
| :-------------------------- | :------------------------------------- | :----------------------------------------------------------- | :------- |
| `file`                      | `string`                               | 服务器可访问的图像文件或PDF文件的URL，或上述类型文件内容的Base64编码结果。默认对于超过10页的PDF文件，只有前10页的内容会被处理。 要解除页数限制，请在产线配置文件中添加以下配置：`Serving:  extra:    max_num_input_imgs: null ` | 是       |
| `fileType`                  | `integer`｜`null`                      | 文件类型。`0`表示PDF文件，`1`表示图像文件。若请求体无此属性，则将根据URL推断文件类型。 | 否       |
| `useDocOrientationClassify` | `boolean` | `null`                     | 请参阅产线对象中 `predict` 方法的 `use_doc_orientation_classify` 参数相关说明。 | 否       |
| `useDocUnwarping`           | `boolean` | `null`                     | 请参阅PaddleOCR-VL对象中 `predict` 方法的 `use_doc_unwarping` 参数相关说明。 | 否       |
| `useLayoutDetection`        | `boolean` | `null`                     | 请参阅PaddleOCR-VL对象中 `predict` 方法的 `use_layout_detection` 参数相关说明。 | 否       |
| `useChartRecognition`       | `boolean` | `null`                     | 请参阅PaddleOCR-VL对象中 `predict` 方法的 `use_chart_recognition` 参数相关说明。 | 否       |
| `layoutThreshold`           | `number` | `object` | `null`           | 请参阅PaddleOCR-VL对象中 `predict` 方法的 `layout_threshold` 参数相关说明。 | 否       |
| `layoutNms`                 | `boolean` | `null`                     | 请参阅PaddleOCR-VL对象中 `predict` 方法的 `layout_nms` 参数相关说明。 | 否       |
| `layoutUnclipRatio`         | `number` | `array` | `object` | `null` | 请参阅PaddleOCR-VL对象中 `predict` 方法的 `layout_unclip_ratio` 参数相关说明。 | 否       |
| `layoutMergeBboxesMode`     | `string` | `object` | `null`           | 请参阅PaddleOCR-VL对象中 `predict` 方法的 `layout_merge_bboxes_mode` 参数相关说明。 | 否       |
| `promptLabel`               | `string` | `null`                      | 请参阅PaddleOCR-VL对象中 `predict` 方法的 `prompt_label` 参数相关说明。 | 否       |
| `formatBlockContent`        | `boolean` | `null`                     | 请参阅PaddleOCR-VL对象中 `predict` 方法的 `format_block_content` 参数相关说明。 | 否       |
| `repetitionPenalty`         | `number` | `null`                      | 请参阅PaddleOCR-VL对象中 `predict` 方法的 `repetition_penalty` 参数相关说明。 | 否       |
| `temperature`               | `number` | `null`                      | 请参阅PaddleOCR-VL对象中 `predict` 方法的 `temperature` 参数相关说明。 | 否       |
| `topP`                      | `number` | `null`                      | 请参阅PaddleOCR-VL对象中 `predict` 方法的 `top_p` 参数相关说明。 | 否       |
| `minPixels`                 | `number` | `null`                      | 请参阅PaddleOCR-VL对象中 `predict` 方法的 `min_pixels` 参数相关说明。 | 否       |
| `maxPixels`                 | `number` | `null`                      | 请参阅PaddleOCR-VL对象中 `predict` 方法的 `max_pixels` 参数相关说明。 | 否       |
| `prettifyMarkdown`          | `boolean`                              | 是否输出美化后的 Markdown 文本。默认为 `true`。              | 否       |
| `showFormulaNumber`         | `boolean`                              | 输出的 Markdown 文本中是否包含公式编号。默认为 `false`。     | 否       |
| `visualize`                 | `boolean` | `null`                     | 是否返回可视化结果图以及处理过程中的中间图像等。传入 `true`：返回图像。传入 `false`：不返回图像。若请求体中未提供该参数或传入 `null`：遵循配置文件`Serving.visualize` 的设置。 例如，在配置文件中添加如下字段： `Serving:  visualize: False `将默认不返回图像，通过请求体中的`visualize`参数可以覆盖默认行为。如果请求体和配置文件中均未设置（或请求体传入`null`、配置文件中未设置），则默认返回图像。 | 否       |

- 请求处理成功时，响应体的`result`具有如下属性：

| 名称                   | 类型     | 含义                                                         |
| :--------------------- | :------- | :----------------------------------------------------------- |
| `layoutParsingResults` | `array`  | 版面解析结果。数组长度为1（对于图像输入）或实际处理的文档页数（对于PDF输入）。对于PDF输入，数组中的每个元素依次表示PDF文件中实际处理的每一页的结果。 |
| `dataInfo`             | `object` | 输入数据信息。                                               |

`layoutParsingResults`中的每个元素为一个`object`，具有如下属性：

| 名称           | 类型              | 含义                                                         |
| :------------- | :---------------- | :----------------------------------------------------------- |
| `prunedResult` | `object`          | 对象的 `predict` 方法生成结果的 JSON 表示中 `res` 字段的简化版本，其中去除了 `input_path` 和 `page_index` 字段。 |
| `markdown`     | `object`          | Markdown结果。                                               |
| `outputImages` | `object` | `null` | 参见预测结果的 `img` 属性说明。图像为JPEG格式，使用Base64编码。 |
| `inputImage`   | `string` | `null` | 输入图像。图像为JPEG格式，使用Base64编码。                   |

`markdown`为一个`object`，具有如下属性：

| 名称      | 类型      | 含义                                           |
| :-------- | :-------- | :--------------------------------------------- |
| `text`    | `string`  | Markdown文本。                                 |
| `images`  | `object`  | Markdown图片相对路径和Base64编码图像的键值对。 |
| `isStart` | `boolean` | 当前页面第一个元素是否为段开始。               |
| `isEnd`   | `boolean` | 当前页面最后一个元素是否为段结束。             |





python调用示例：



```python
import base64
import requests
import pathlib

API_URL = "http://localhost:8080/layout-parsing" # 服务URL

image_path = "./demo.jpg"

# 对本地图像进行Base64编码
with open(image_path, "rb") as file:
    image_bytes = file.read()
    image_data = base64.b64encode(image_bytes).decode("ascii")

payload = {
    "file": image_data, # Base64编码的文件内容或者文件URL
    "fileType": 1, # 文件类型，1表示图像文件
}

# 调用API
response = requests.post(API_URL, json=payload)

# 处理接口返回数据
assert response.status_code == 200
result = response.json()["result"]
for i, res in enumerate(result["layoutParsingResults"]):
    print(res["prunedResult"])
    md_dir = pathlib.Path(f"markdown_{i}")
    md_dir.mkdir(exist_ok=True)
    (md_dir / "doc.md").write_text(res["markdown"]["text"])
    for img_path, img in res["markdown"]["images"].items():
        img_path = md_dir / img_path
        img_path.parent.mkdir(parents=True, exist_ok=True)
        img_path.write_bytes(base64.b64decode(img))
    print(f"Markdown document saved at {md_dir / 'doc.md'}")
    for img_name, img in res["outputImages"].items():
        img_path = f"{img_name}_{i}.jpg"
        pathlib.Path(img_path).parent.mkdir(exist_ok=True)
        with open(img_path, "wb") as f:
            f.write(base64.b64decode(img))
        print(f"Output image saved at {img_path}")
```

