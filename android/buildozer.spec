[app]
title = BierAlarm
package.name = bieralarm
package.domain = io.github.urtyp50
source.dir = .
source.include_exts = py,png
source.exclude_dirs = bin,.buildozer,__pycache__
version = 0.1.0
requirements = python3,kivy==2.3.0,pypdf,certifi,tzdata,plyer
orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/icon.png
android.presplash_color = #121517
android.permissions = INTERNET, ACCESS_NETWORK_STATE, POST_NOTIFICATIONS
android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 0
