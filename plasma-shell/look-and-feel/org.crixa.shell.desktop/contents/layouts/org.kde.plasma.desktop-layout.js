var panel = new Panel
var geo = screenGeometry(panel.screen)
var panelWidth = Math.min(Math.round(geo.width * 0.82), Math.round(geo.height * 1.92))

panel.location = "bottom"
panel.height = 2 * Math.floor(gridUnit * 3.2 / 2)
panel.alignment = "center"
panel.minimumLength = panelWidth
panel.maximumLength = panelWidth
panel.floating = true

var tasks = panel.addWidget("org.kde.plasma.icontasks")
tasks.currentConfigGroup = ["General"]
tasks.writeConfig("launchers", "applications:crixa-launcher.desktop,applications:crixa-browser.desktop,applications:crixa-files.desktop,applications:crixa-terminal.desktop,applications:crixa-store.desktop,applications:crixa-settings.desktop")
tasks.writeConfig("showOnlyCurrentScreen", true)
tasks.writeConfig("showOnlyCurrentDesktop", false)
tasks.writeConfig("showOnlyCurrentActivity", false)
tasks.writeConfig("groupingStrategy", 1)
tasks.writeConfig("groupPopups", false)
tasks.writeConfig("onlyGroupWhenFull", true)
tasks.writeConfig("separateLaunchers", true)
tasks.writeConfig("sortingStrategy", 1)
tasks.writeConfig("fill", false)
tasks.writeConfig("iconSpacing", 6)
tasks.writeConfig("wheelEnabled", false)

var stretch = panel.addWidget("org.kde.plasma.panelspacer")
stretch.currentConfigGroup = ["General"]
stretch.writeConfig("expanding", true)

var tray = panel.addWidget("org.kde.plasma.systemtray")
tray.currentConfigGroup = ["General"]
tray.writeConfig("scaleIconsToFit", true)
tray.writeConfig("iconSpacing", 1)
tray.writeConfig("shownItems", "org.kde.plasma.notifications,org.kde.plasma.networkmanagement,org.kde.plasma.volume,org.kde.plasma.bluetooth,org.kde.plasma.battery")
tray.writeConfig("hiddenItems", "org.kde.plasma.clipboard")

var clock = panel.addWidget("org.kde.plasma.digitalclock")
clock.currentConfigGroup = ["Appearance"]
clock.writeConfig("showDate", true)
clock.writeConfig("dateFormat", "custom")
clock.writeConfig("customDateFormat", "ddd MMM d")
clock.writeConfig("use24hFormat", 1)
clock.writeConfig("dateDisplayFormat", "BesideTime")
clock.writeConfig("showSeconds", false)
clock.writeConfig("autoFontAndSize", false)
clock.writeConfig("fontFamily", "IBM Plex Sans")
clock.writeConfig("fontSize", 10)
clock.writeConfig("fontWeight", 57)

var desktopsArray = desktopsForActivity(currentActivity())
for (var j = 0; j < desktopsArray.length; j++) {
    desktopsArray[j].wallpaperPlugin = "org.kde.image"
    desktopsArray[j].currentConfigGroup = ["General"]
    desktopsArray[j].writeConfig("toolTips", false)
    desktopsArray[j].writeConfig("selectionMarkers", false)
    desktopsArray[j].writeConfig("previews", false)
    desktopsArray[j].writeConfig("popups", false)
    desktopsArray[j].writeConfig("labelMode", 0)
}
