@echo off
chcp 65001 > nul
set GRADLE_USER_HOME=D:\gradle-home
set ANDROID_HOME=D:\AndroidSdk
set ANDROID_SDK_ROOT=D:\AndroidSdk
set JAVA_HOME=D:\Android\Sdk\jbr
set NODE_ENV=production
set PATH=%ANDROID_HOME%\platform-tools;%JAVA_HOME%\bin;%PATH%

cd /d D:\autoglm-mobile-work\mobile-app
call npx expo export --platform android --output-dir dist-bundle

cd /d D:\autoglm-mobile-work\mobile-app\android
call gradlew.bat assembleRelease

if exist app\build\outputs\apk\release\app-release.apk (
  if not exist D:\autoglm-mobile-work\dist mkdir D:\autoglm-mobile-work\dist
  copy /Y app\build\outputs\apk\release\app-release.apk D:\autoglm-mobile-work\dist\AutoGLM-Mobile-Copilot.apk
  echo APK copied to D:\autoglm-mobile-work\dist\AutoGLM-Mobile-Copilot.apk
)
