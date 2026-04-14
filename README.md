# qrcode-extract

Windows 本地扫码接收程序（用于接收云桌面动态二维码传输文件）。

## 功能覆盖

- 可拖拽窗口（按住顶部标题栏拖动）。
- 对准二维码后，点击“开始扫描”触发接收。
- 扫描在线程中执行，窗口被其他程序遮挡不影响扫描。
- 接收完成后文件列表展示，可复制路径或文本内容。

## 运行

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

## 支持的二维码分片格式

1. JSON 格式：

```json
{"fileId":"abc","fileName":"demo.txt","seq":0,"total":3,"data":"<base64-chunk>"}
```

2. 文本格式：

```text
FILE::abc::demo.txt::0/3::<base64-chunk>
```

> 说明：如果 `cimbar_js` 输出格式不同，需要在 `app.py` 的 `_parse_chunk_payload` 中补充解析规则。
