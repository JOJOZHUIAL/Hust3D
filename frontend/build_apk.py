# -*- coding: utf-8 -*-
"""安卓 APK 一键打包：构建前端 -> 同步 -> 英文路径镜像 -> Gradle 打包 -> 拷回。

用法：双击 build_apk.bat（内部调用本脚本），或 python build_apk.py
产物：android/app/build/outputs/apk/debug/app-debug.apk
"""
import os
import shutil
import subprocess
import sys

FRONTEND = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(FRONTEND)
BUILD_DIR = r"C:\hust3d-android"
JAVA_HOME = r"C:\Program Files\Microsoft\jdk-21.0.11.10-hotspot"
SDK_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")
APK_SRC = os.path.join(BUILD_DIR, "app", "build", "outputs", "apk", "debug", "app-debug.apk")
APK_DST = os.path.join(FRONTEND, "android", "app", "build", "outputs", "apk", "debug", "app-debug.apk")


def run(cmd, cwd=None, check=True, shell=False):
    print("+", cmd if isinstance(cmd, str) else " ".join(cmd))
    env = dict(os.environ)
    if JAVA_HOME and os.path.isdir(JAVA_HOME):
        env["JAVA_HOME"] = JAVA_HOME
    r = subprocess.run(cmd, cwd=cwd, env=env, shell=shell)
    if check and r.returncode != 0:
        print(f"[ERROR] 命令失败（退出码 {r.returncode}）：{cmd}")
        sys.exit(1)
    return r


def main():
    os.chdir(FRONTEND)

    print("[1/5] 构建前端...")
    run("npm run build", shell=True)

    print("[2/5] 同步到安卓工程...")
    run("npx cap sync android", shell=True)

    print("[3/5] 准备英文路径构建目录（项目路径含中文，需镜像到 %s）..." % BUILD_DIR)
    # 清掉镜像里的旧构建产物，保留 Gradle 缓存以加速
    old_build = os.path.join(BUILD_DIR, "app", "build")
    if os.path.isdir(old_build):
        shutil.rmtree(old_build, ignore_errors=True)
    mirror_src = os.path.join(FRONTEND, "android")
    if os.path.isdir(BUILD_DIR):
        for name in os.listdir(BUILD_DIR):
            p = os.path.join(BUILD_DIR, name)
            if name == "capacitor-android":
                continue  # 单独覆盖
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
    shutil.copytree(mirror_src, BUILD_DIR,
                    ignore=shutil.ignore_patterns(".gradle", "build", "capacitor-android"),
                    dirs_exist_ok=True)
    # 镜像内所有 Capacitor 模块（含各插件）改为本地引用：
    # capacitor.settings.gradle 里的 ../node_modules/... 相对路径在镜像中失效，
    # 逐个把引用的模块目录拷进镜像 plugins/ 下并重写路径
    import re
    settings = os.path.join(BUILD_DIR, "capacitor.settings.gradle")
    with open(settings, encoding="utf-8") as f:
        s = f.read()

    def _localize(m):
        proj, rel = m.groups()
        src = os.path.normpath(os.path.join(FRONTEND, "node_modules", rel))
        dest = os.path.join(BUILD_DIR, "plugins", proj.lstrip(":"))
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest, dirs_exist_ok=True)
        return f"project('{proj}').projectDir = new File('plugins/{proj.lstrip(':')}')"

    s = re.sub(r"project\('([^']+)'\)\.projectDir = new File\('\.\./node_modules/([^']+)'\)", _localize, s)
    with open(settings, "w", encoding="utf-8") as f:
        f.write(s)

    # local.properties：sdk.dir 必须用正斜杠（Properties 会吃反斜杠）
    sdk_prop = "sdk.dir=" + SDK_DIR.replace("\\", "/") + "\n"
    for d in (BUILD_DIR, mirror_src):
        with open(os.path.join(d, "local.properties"), "w", encoding="ascii") as f:
            f.write(sdk_prop)

    print("[4/5] Gradle 打包（首次约 5 分钟，之后增量很快）...")
    gradlew = os.path.join(BUILD_DIR, "gradlew.bat")
    run([gradlew, "assembleDebug", "--no-daemon"], cwd=BUILD_DIR)

    print("[5/5] 拷回 APK...")
    os.makedirs(os.path.dirname(APK_DST), exist_ok=True)
    shutil.copy2(APK_SRC, APK_DST)
    size_mb = os.path.getsize(APK_DST) / 1024 / 1024
    print()
    print("=" * 40)
    print(f"APK 已生成（{size_mb:.1f} MB）：")
    print(APK_DST.replace(PROJECT + os.sep, ""))
    print("传到手机安装即可（首次需允许安装未知来源应用）。")
    print("=" * 40)


if __name__ == "__main__":
    main()
