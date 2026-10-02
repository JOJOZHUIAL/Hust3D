# 安卓 App（APK）打包与使用说明

把系统打包成安卓 App 后，摄像头由**原生 App 授权**，不再受"必须 HTTPS"的浏览器限制，
局域网 http 地址即可扫码，也不用再点自签名证书警告。

## 一、打包（在开发电脑上）

前提：JDK 21（本机已装）、Node。Android SDK 首次打包时脚本会自动安装
（已装好：`%LOCALAPPDATA%\Android\Sdk`，含 platform-35 / build-tools 35）。

双击运行：

```
frontend\build_apk.bat
```

产物：`frontend\android\app\build\outputs\apk\debug\app-debug.apk`

改了前端代码后重新打包：改完直接再跑一次 `build_apk.bat`（会重新构建前端并同步进 APK）。

## 二、安装到手机

1. 把 `app-debug.apk` 传到手机（微信文件传输 / 数据线 / 局域网均可）；
2. 手机上点开安装；系统提示「未知来源应用」时允许安装；
3. 安装后打开「3D打印服务」App。

> debug 签名的 APK 直接安装即可；正式分发给别人可长期使用，无需每次重装。

## 三、App 内配置（每次换服务器才需要）

1. 打开 App → 登录页第一行「**服务器**」填写电脑上的后端地址：
   ```
   http://192.168.1.150:5000
   ```
   （与电脑同一 Wi-Fi；地址 = 电脑 IP + 5000 端口，电脑上 `ipconfig` 可查）
2. 正常输入学号密码登录；
3. 「管理后台 → 耗材管理」点「开始扫码」——**首次会弹摄像头权限，点允许**，对准条形码即可。

「我的 → 服务器地址」可随时查看；点「清除重设」可改连别的服务器。

## 四、常见问题

| 问题 | 处理 |
|---|---|
| App 提示网络异常 | 检查登录页服务器地址是否正确；手机与电脑是否同一 Wi-Fi；电脑防火墙是否放行 5000 端口 |
| 点开始扫码没反应 | 首次使用需允许摄像头权限；到系统设置 → 应用 → 3D打印服务 → 权限 → 相机 → 允许 |
| 电脑 IP 变了 | App 登录页改一下服务器地址即可；电脑想固定 IP 可在路由器绑定 DHCP |
| 想改 App 名称/图标 | `frontend\capacitor.config.json` 的 appName；图标在 `android\app\src\main\res` 下各 mipmap 目录 |

## 五、打包原理（给维护者）

- 前端 Vue SPA 通过 Capacitor 打进 APK，App 内页面由本机 `https://localhost` 加载
  （Capacitor 默认 androidScheme=https），属于安全上下文，WebView 的 getUserMedia 摄像头可用；
- API 请求与上传资源在 App 模式下统一指向登录页设置的服务器地址
  （`src/utils/server.js` + `api/request.js` 拦截器动态 baseURL）；
- App 允许混合内容（`capacitor.config.json` 的 `android.allowMixedContent`），
  因此 https 页面可以请求局域网 http 接口；
- 扫码仍是页面内 html5-qrcode（WebView 摄像头），语音录制的麦克风权限也已声明。

## 六、构建环境踩坑记录（本项目实际遇到）

| 问题 | 解决 |
|---|---|
| Gradle 发行包下载报 SSL 证书链错误 | `android/gradle/wrapper/gradle-wrapper.properties` 的 distributionUrl 已换腾讯镜像；Maven 仓库已加阿里云镜像（`android/build.gradle`） |
| 项目路径含中文（三维科创3D）导致 AGP 拒绝构建 | `build_apk.bat` 把 android 工程镜像到 `C:\hust3d-android`（纯英文）再构建，APK 拷回项目；`gradle.properties` 已加 `android.overridePathCheck=true` |
| `local.properties` 的 sdk.dir 反斜杠被 Properties 转义吃掉，报"文件名、目录名或卷标语法不正确" | sdk.dir 必须用正斜杠：`C:/Users/ROG/AppData/Local/Android/Sdk` |
| 镜像目录里 Capacitor 模块相对路径失效（No variants exist） | 模块拷到镜像内并改 `capacitor.settings.gradle` 指向本地 `capacitor-android`（脚本已处理） |
