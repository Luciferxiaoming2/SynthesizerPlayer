import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1480
    height: 920
    minimumWidth: 920
    minimumHeight: 620
    visible: true
    title: "Synthesizer Player"
    color: "#07080d"

    property var bridge: audioWorkbench
    property string fileTarget: "vocal"
    property color bg: "#07080d"
    property color surface: "#0b0c12"
    property color panel: "#10121b"
    property color panelSoft: "#151722"
    property color panelLine: "#242635"
    property color accent: "#e12a83"
    property color accent2: "#ff55ad"
    property color teal: "#10d5a6"
    property color textMain: "#f8f5fb"
    property color textMuted: "#9aa0ad"
    property color textDim: "#687080"
    property real designWidth: 1480
    property real designHeight: 920
    property real uiScale: Math.max(0.62, Math.min(1.35, Math.min(width / designWidth, height / designHeight)))
    property real tonePreviewValue: 0.4
    property int rewriteLyricIndex: -1

    function modelIndex(model, value) {
        if (!model)
            return -1
        for (var i = 0; i < model.length; i++) {
            if (model[i] === value)
                return i
        }
        return -1
    }

    function selectedSeparatorBackend() {
        if (!root.bridge || separatorPicker.currentIndex < 0)
            return "demucs"
        return root.bridge.separatorBackends[separatorPicker.currentIndex]
    }

    function selectedLyricsBackend() {
        if (!root.bridge || lyricsBackendPicker.currentIndex < 0)
            return "preview"
        return root.bridge.lyricsBackends[lyricsBackendPicker.currentIndex]
    }

    function htmlEscape(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
    }

    function lyricProgressHtml(value, progress, active, sung) {
        if (!active)
            return htmlEscape(value)
        var text = String(value || "")
        var tokens = text.match(/[\u3400-\u9fff]|[A-Za-z0-9]+|[^A-Za-z0-9\u3400-\u9fff]/g) || []
        var countable = 0
        for (var i = 0; i < tokens.length; i++) {
            if (/[\u3400-\u9fff]|[A-Za-z0-9]+/.test(tokens[i]))
                countable += 1
        }
        var sungLimit = Math.floor(countable * Math.max(0, Math.min(1, progress || 0)))
        var seen = 0
        var html = ""
        for (var j = 0; j < tokens.length; j++) {
            var token = tokens[j]
            var isCountable = /[\u3400-\u9fff]|[A-Za-z0-9]+/.test(token)
            var isPast = isCountable && seen < sungLimit
            if (isCountable)
                seen += 1
            html += isPast
                ? "<span style='font-size:25px;color:#ff55ad;font-weight:800'>" + htmlEscape(token) + "</span>"
                : "<span style='font-size:17px;color:#a97798;font-weight:700'>" + htmlEscape(token) + "</span>"
        }
        return html
    }

    Component.onCompleted: {
        if (root.bridge) {
            root.bridge.refreshAudioDevices()
            root.bridge.scanSongs()
        }
    }

    FileDialog {
        id: inputDialog
        title: "选择音频或歌词文件"
        onAccepted: if (root.bridge) root.bridge.setPathFromUrl(root.fileTarget, selectedFile.toString())
    }

    FileDialog {
        id: songImportDialog
        title: "导入完整歌曲"
        nameFilters: ["音频文件 (*.wav *.mp3 *.flac *.ogg *.m4a *.aac)", "所有文件 (*)"]
        onAccepted: if (root.bridge) root.bridge.importSongWithBackendsAsync(selectedFile.toString(), root.selectedSeparatorBackend(), root.selectedLyricsBackend())
    }

    FileDialog {
        id: outputDialog
        title: "选择导出文件"
        fileMode: FileDialog.SaveFile
        nameFilters: ["MP3 文件 (*.mp3)", "Wave 文件 (*.wav)"]
        onAccepted: if (root.bridge) root.bridge.setPathFromUrl("output", selectedFile.toString())
    }

    FolderDialog {
        id: songsFolderDialog
        title: "选择歌曲目录"
        onAccepted: if (root.bridge) root.bridge.setSongsRootFromUrl(selectedFolder.toString())
    }

    FileDialog {
        id: vstPluginDialog
        title: "选择主输出 VST 插件"
        nameFilters: ["VST 插件 (*.vst3 *.dll)", "所有文件 (*)"]
        onAccepted: if (root.bridge) root.bridge.setMasterPluginFromUrl(selectedFile.toString())
    }

    Popup {
        id: statusPopup
        anchors.centerIn: parent
        width: Math.min(parent.width * 0.62, 720)
        modal: false
        focus: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 18

        background: Rectangle {
            radius: 8
            color: "#17101a"
            border.color: root.accent
            opacity: 0.98
        }

        Text {
            width: parent.width
            text: root.bridge ? root.bridge.status : ""
            color: root.textMain
            font.pixelSize: 15
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }
    }

    Popup {
        id: lyricsConfirmPopup
        anchors.centerIn: parent
        width: Math.min(parent.width * 0.58, 560)
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0
        property string message: "这首歌没有可用歌词。是否现在生成歌词？"

        background: Rectangle {
            radius: 10
            color: "#10121b"
            border.color: "#34384a"
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 16

            Text {
                text: "需要歌词吗？"
                color: root.textMain
                font.pixelSize: 20
                font.bold: true
                Layout.fillWidth: true
            }
            Text {
                text: lyricsConfirmPopup.message
                color: root.textMuted
                font.pixelSize: 14
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                SecondaryButton {
                    text: "暂不生成"
                    Layout.preferredWidth: 110
                    onClicked: lyricsConfirmPopup.close()
                }
                PrimaryButton {
                    text: "生成歌词"
                    Layout.preferredWidth: 120
                    onClicked: {
                        lyricsConfirmPopup.close()
                        if (root.bridge)
                            root.bridge.generateSmartLyrics()
                    }
                }
            }
        }
    }

    Popup {
        id: rewritePopup
        anchors.centerIn: parent
        width: Math.min(parent.width * 0.62, 620)
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0
        property string originalLyric: ""

        background: Rectangle {
            radius: 10
            color: "#10121b"
            border.color: "#34384a"
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 14

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "实验版改词唱"
                    color: root.textMain
                    font.pixelSize: 20
                    font.bold: true
                    Layout.fillWidth: true
                }
                Text {
                    text: root.rewriteLyricIndex >= 0 ? ("第 " + (root.rewriteLyricIndex + 1) + " 句") : "未选择"
                    color: root.accent2
                    font.pixelSize: 13
                }
            }
            Text {
                text: "原歌词：" + rewritePopup.originalLyric
                color: root.textMuted
                font.pixelSize: 13
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            TextArea {
                id: rewriteText
                placeholderText: "输入要改唱的新歌词"
                text: rewritePopup.originalLyric
                wrapMode: TextArea.Wrap
                selectByMouse: true
                Layout.fillWidth: true
                Layout.preferredHeight: 108
                color: root.textMain
                background: Rectangle {
                    radius: 8
                    color: "#151722"
                    border.color: "#303447"
                }
            }
            ColumnLayout {
                visible: root.bridge && root.bridge.lyricRewriteBusy
                Layout.fillWidth: true
                spacing: 6
                Text {
                    text: root.bridge ? root.bridge.lyricRewriteStatus : "正在生成改词唱"
                    color: root.textMuted
                    font.pixelSize: 12
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                ProgressBar {
                    from: 0
                    to: 100
                    value: root.bridge ? root.bridge.lyricRewriteProgress : 0
                    indeterminate: root.bridge && root.bridge.lyricRewriteBusy && root.bridge.lyricRewriteProgress < 95
                    Layout.fillWidth: true
                }
            }
            Text {
                text: "当前先使用轻量 preview 合成验证流程；真实唱腔模型接入后会替换这里的合成后端。"
                color: root.textDim
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                SecondaryButton {
                    text: "恢复原唱"
                    Layout.preferredWidth: 110
                    onClicked: if (root.bridge) root.bridge.reloadOriginalVocal()
                }
                Item { Layout.fillWidth: true }
                SecondaryButton {
                    text: "取消"
                    Layout.preferredWidth: 88
                    onClicked: rewritePopup.close()
                }
                PrimaryButton {
                    text: root.bridge && root.bridge.lyricRewriteBusy ? "生成中" : "生成试听"
                    enabled: !(root.bridge && root.bridge.lyricRewriteBusy)
                    Layout.preferredWidth: 120
                    onClicked: {
                        if (root.bridge)
                            root.bridge.generateLyricRewrite(root.rewriteLyricIndex, rewriteText.text)
                    }
                }
            }
        }
    }

    Timer {
        id: statusPopupTimer
        interval: 3200
        repeat: false
        onTriggered: statusPopup.close()
    }

    Timer {
        id: toneApplyTimer
        interval: 280
        repeat: false
        onTriggered: {
            toneSlider.value = root.tonePreviewValue
            if (root.bridge)
                root.bridge.setToneDeafRatio(root.tonePreviewValue)
        }
    }

    Connections {
        target: root.bridge
        function onStatusChanged() {
            if (!root.bridge || root.bridge.status === "" || root.bridge.status === "Ready")
                return
            statusPopup.open()
            statusPopupTimer.restart()
        }
        function onLyricsGenerationPromptRequested(message) {
            lyricsConfirmPopup.message = message
            lyricsConfirmPopup.open()
        }
        function onLyricPositionChanged() {
            if (root.bridge && root.bridge.currentLyricIndex >= 0)
                Qt.callLater(function() {
                    lyricList.positionViewAtIndex(root.bridge.currentLyricIndex, ListView.Center)
                })
        }
        function onSongsChanged() {
            if (root.bridge && root.bridge.currentSongIndex >= 0)
                songList.currentIndex = root.bridge.currentSongIndex
        }
    }

    Popup {
        id: settingsPopup
        x: root.width - width - 18 * root.uiScale
        y: topBar.height * root.uiScale + 10 * root.uiScale
        width: Math.min(root.width - 36 * root.uiScale, 420 * root.uiScale)
        height: Math.min(root.height - topBar.height * root.uiScale - bottomBar.height * root.uiScale - 28 * root.uiScale, 760 * root.uiScale)
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0

        background: Rectangle {
            color: "#0d0f17"
            radius: 10
            border.color: "#2a2d3c"
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 14

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "设置"
                    color: root.textMain
                    font.pixelSize: 20
                    font.bold: true
                    Layout.fillWidth: true
                }
                IconButton {
                    label: "×"
                    tip: "关闭"
                    onClicked: settingsPopup.close()
                }
            }

            Flickable {
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: width
                contentHeight: settingsContent.implicitHeight
                clip: true

                ColumnLayout {
                    id: settingsContent
                    width: parent.width
                    spacing: 12

                    SettingsLabel { text: "导入与歌曲库" }
                PrimaryButton {
                    text: root.bridge && root.bridge.importBusy ? "导入中" : "智能分轨导入歌曲"
                    enabled: !(root.bridge && root.bridge.importBusy)
                    Layout.fillWidth: true
                    onClicked: songImportDialog.open()
                }
                ColumnLayout {
                    visible: root.bridge && root.bridge.importBusy
                    Layout.fillWidth: true
                    spacing: 6
                    Text {
                        text: root.bridge ? root.bridge.importProgressStatus : "正在导入歌曲"
                        color: root.textMuted
                        font.pixelSize: 12
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    ProgressBar {
                        from: 0
                        to: 100
                        value: root.bridge ? root.bridge.importProgress : 0
                        indeterminate: root.bridge && root.bridge.importProgressIndeterminate
                        Layout.fillWidth: true
                    }
                }
                    RowLayout {
                        Layout.fillWidth: true
                        SecondaryButton {
                            text: "选择目录"
                            Layout.fillWidth: true
                            onClicked: songsFolderDialog.open()
                        }
                        SecondaryButton {
                            text: "扫描本地"
                            Layout.fillWidth: true
                            onClicked: if (root.bridge) root.bridge.scanSongs()
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        SecondaryButton {
                            text: "加载选中"
                            Layout.fillWidth: true
                            onClicked: if (root.bridge) root.bridge.loadSongAt(songList.currentIndex)
                        }
                        SecondaryButton {
                            text: "删除选中"
                            Layout.fillWidth: true
                            onClicked: if (root.bridge) root.bridge.deleteSongAt(songList.currentIndex)
                        }
                    }
                    SecondaryButton {
                        text: "清空列表"
                        Layout.fillWidth: true
                        onClicked: if (root.bridge) root.bridge.clearSongList()
                    }

                    SettingsLabel { text: "歌词与分离" }
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "分离方式"
                            color: root.textMuted
                            font.pixelSize: 13
                            Layout.preferredWidth: 86
                        }
                        ComboBox {
                            id: separatorPicker
                            model: root.bridge ? root.bridge.separatorBackendLabels : []
                            currentIndex: root.bridge ? Math.max(0, root.modelIndex(root.bridge.separatorBackends, root.bridge.separatorBackend)) : 0
                            Layout.fillWidth: true
                            onActivated: if (root.bridge) root.bridge.setSeparatorBackend(root.selectedSeparatorBackend())
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "歌词方式"
                            color: root.textMuted
                            font.pixelSize: 13
                            Layout.preferredWidth: 86
                        }
                        ComboBox {
                            id: lyricsBackendPicker
                            model: root.bridge ? root.bridge.lyricsBackendLabels : []
                            currentIndex: 0
                            Layout.fillWidth: true
                            onActivated: if (root.bridge) root.bridge.setLyricsBackend(root.selectedLyricsBackend())
                        }
                    }
                    Text {
                        text: root.bridge ? root.bridge.lyricsBackendStatus : ""
                        color: root.textMuted
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        SecondaryButton {
                            text: "生成歌词"
                            Layout.fillWidth: true
                            onClicked: if (root.bridge) root.bridge.generateLyrics()
                        }
                        SecondaryButton {
                            text: "导入歌词"
                            Layout.fillWidth: true
                            onClicked: {
                                root.fileTarget = "lyrics"
                                inputDialog.nameFilters = ["歌词文件 (*.lrc *.srt)", "所有文件 (*)"]
                                inputDialog.open()
                            }
                        }
                    }

                    SettingsLabel { text: "输出与插件" }
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "输出设备"
                            color: root.textMuted
                            font.pixelSize: 13
                            Layout.preferredWidth: 86
                        }
                        ComboBox {
                            id: audioDevicePicker
                            model: root.bridge ? root.bridge.audioDeviceNames : []
                            currentIndex: root.bridge ? root.bridge.selectedAudioDeviceIndex : -1
                            Layout.fillWidth: true
                            onActivated: if (root.bridge) root.bridge.selectAudioDevice(index)
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        SecondaryButton {
                            text: "刷新设备"
                            Layout.fillWidth: true
                            onClicked: if (root.bridge) root.bridge.refreshAudioDevices()
                        }
                        SecondaryButton {
                            text: "选择导出"
                            Layout.fillWidth: true
                            onClicked: outputDialog.open()
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        SecondaryButton {
                            text: "加载 VST"
                            Layout.fillWidth: true
                            onClicked: vstPluginDialog.open()
                        }
                        SecondaryButton {
                            text: "移除 VST"
                            enabled: root.bridge && root.bridge.masterPluginPath
                            Layout.fillWidth: true
                            onClicked: if (root.bridge) root.bridge.clearMasterPlugin()
                        }
                    }

                    SettingsLabel { text: "实验功能" }
                    RowLayout {
                        Layout.fillWidth: true
                        SecondaryButton {
                            text: "生成样例"
                            Layout.fillWidth: true
                            onClicked: if (root.bridge) root.bridge.generateMockAudio()
                        }
                        SecondaryButton {
                            text: "检测对齐"
                            Layout.fillWidth: true
                            onClicked: if (root.bridge) root.bridge.evaluateAlignment()
                        }
                    }
                    SecondaryButton {
                        text: root.bridge && root.bridge.lyricRewriteBusy ? "改词唱生成中" : "改词唱实验版"
                        enabled: !(root.bridge && root.bridge.lyricRewriteBusy)
                        Layout.fillWidth: true
                        onClicked: {
                            root.rewriteLyricIndex = root.bridge ? root.bridge.currentLyricIndex : -1
                            rewritePopup.originalLyric = root.bridge && root.bridge.currentLyric.length > 0 ? root.bridge.currentLyric : ""
                            rewriteText.text = rewritePopup.originalLyric
                            rewritePopup.open()
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        id: appFrame
        width: root.width / root.uiScale
        height: root.height / root.uiScale
        transformOrigin: Item.TopLeft
        scale: root.uiScale
        color: root.bg

        Rectangle {
            id: topBar
            height: 70
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            color: "#0b0c12"
            border.color: "#171923"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 24
                anchors.rightMargin: 22
                spacing: 14

                Rectangle {
                    Layout.preferredWidth: 13
                    Layout.preferredHeight: 13
                    radius: 7
                    color: root.accent2
                }

                Text {
                    text: "Synthesizer Player"
                    color: root.textMain
                    font.pixelSize: 22
                    font.bold: true
                    font.letterSpacing: 0
                    Layout.fillWidth: true
                }

                Rectangle {
                    Layout.preferredWidth: 356
                    Layout.preferredHeight: 36
                    radius: 18
                    color: "#151723"
                    border.color: "#272b3b"
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16
                        anchors.rightMargin: 16
                        spacing: 8
                        Rectangle {
                            Layout.preferredWidth: 8
                            Layout.preferredHeight: 8
                            radius: 4
                            color: root.teal
                        }
                        Text {
                            text: root.bridge && root.bridge.audioDeviceNames.length > 0 ? ("输出设备: " + root.bridge.audioDeviceNames[Math.max(0, root.bridge.selectedAudioDeviceIndex)]) : "输出设备: 系统默认"
                            color: "#c8c2ce"
                            font.pixelSize: 16
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                }

                IconButton {
                    label: "⚙"
                    tip: "设置"
                    onClicked: settingsPopup.open()
                }
            }
        }

        Rectangle {
            id: leftPane
            width: 318
            anchors.left: parent.left
            anchors.top: topBar.bottom
            anchors.bottom: bottomBar.top
            color: "#0d0f16"
            border.color: "#1e212c"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 14

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 45
                    radius: 9
                    color: "#151822"
                    border.color: "#282b38"
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 15
                        anchors.rightMargin: 12
                        spacing: 10
                        Text {
                            text: "⌕"
                            color: root.textMuted
                            font.pixelSize: 20
                        }
                        Text {
                            text: "搜索歌曲..."
                            color: root.textMuted
                            font.pixelSize: 14
                            Layout.fillWidth: true
                        }
                    }
                }

                Text {
                    text: "保存歌曲库"
                    color: root.textMuted
                    font.pixelSize: 13
                    Layout.leftMargin: 5
                }

                ListView {
                    id: songList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 10
                    model: root.bridge ? root.bridge.songNames : []
                    currentIndex: root.bridge && root.bridge.currentSongIndex >= 0 ? root.bridge.currentSongIndex : 0
                    delegate: Rectangle {
                        width: songList.width
                        height: 66
                        radius: 9
                        color: ListView.isCurrentItem ? "#2a0e21" : "#0f1118"
                        border.color: ListView.isCurrentItem ? "#6d214b" : "transparent"

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 10
                            Rectangle {
                                Layout.preferredWidth: 40
                                Layout.preferredHeight: 40
                                radius: 5
                                color: ListView.isCurrentItem ? "#5b1741" : "#181c28"
                                Text {
                                    anchors.centerIn: parent
                                    text: "♫"
                                    color: ListView.isCurrentItem ? root.accent2 : root.textDim
                                    font.pixelSize: 21
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    text: modelData
                                    color: ListView.isCurrentItem ? root.accent2 : root.textMain
                                    font.pixelSize: 16
                                    font.bold: ListView.isCurrentItem
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Text {
                                    text: index === songList.currentIndex ? "当前播放" : "Synthesizer"
                                    color: root.textMuted
                                    font.pixelSize: 13
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }
                            Text {
                                text: index === songList.currentIndex ? (root.bridge ? root.bridge.playbackTime.split(" / ")[1] : "00:00") : "--:--"
                                color: root.textMuted
                                font.pixelSize: 12
                                font.family: "Consolas"
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            onClicked: songList.currentIndex = index
                            onDoubleClicked: if (root.bridge) root.bridge.loadSongAt(index)
                        }
                    }
                }

                PrimaryButton {
                    text: "+  真实分离导入歌曲"
                    enabled: !(root.bridge && root.bridge.importBusy)
                    Layout.fillWidth: true
                    Layout.preferredHeight: 56
                    onClicked: songImportDialog.open()
                }

                ColumnLayout {
                    visible: root.bridge && root.bridge.importBusy
                    Layout.fillWidth: true
                    spacing: 6
                    Text {
                        text: root.bridge ? root.bridge.importProgressStatus : "正在导入歌曲"
                        color: root.textMuted
                        font.pixelSize: 12
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    ProgressBar {
                        from: 0
                        to: 100
                        value: root.bridge ? root.bridge.importProgress : 0
                        indeterminate: root.bridge && root.bridge.importProgressIndeterminate
                        Layout.fillWidth: true
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    SecondaryButton {
                        text: "⇧ 导入伴奏"
                        Layout.fillWidth: true
                        onClicked: {
                            root.fileTarget = "instrumental"
                            inputDialog.nameFilters = ["音频文件 (*.wav *.mp3 *.flac *.ogg *.m4a *.aac)", "所有文件 (*)"]
                            inputDialog.open()
                        }
                    }
                    SecondaryButton {
                        text: "⌕ 扫描 save"
                        Layout.fillWidth: true
                        onClicked: if (root.bridge) root.bridge.scanSongs()
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    SecondaryButton {
                        text: "删除选中"
                        enabled: root.bridge && root.bridge.songNames.length > 0
                        Layout.fillWidth: true
                        onClicked: if (root.bridge) root.bridge.deleteSongAt(songList.currentIndex)
                    }
                    SecondaryButton {
                        text: "清空列表"
                        enabled: root.bridge && root.bridge.songNames.length > 0
                        Layout.fillWidth: true
                        onClicked: if (root.bridge) root.bridge.clearSongList()
                    }
                }
            }
        }

        Rectangle {
            id: rightPane
            width: 384
            anchors.top: topBar.bottom
            anchors.right: parent.right
            anchors.bottom: bottomBar.top
            color: "#0c0e15"
            border.color: "#1e212c"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: 16

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: "● F0 音高基频监视器"
                        color: root.textMain
                        font.pixelSize: 16
                        font.bold: true
                        Layout.fillWidth: true
                    }
                    Text {
                        text: root.bridge ? root.bridge.sampleRateLabel : "未加载"
                        color: root.textMuted
                        font.pixelSize: 12
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 194
                    radius: 14
                    color: "#10131d"
                    border.color: "#252a39"
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 12
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "基频实时破坏状态"
                                color: root.textDim
                                font.pixelSize: 12
                                Layout.fillWidth: true
                            }
                            Text {
                                text: root.bridge ? (Math.round(root.bridge.toneDeafRatio * 100) + "% 跑调") : "0% 跑调"
                                color: root.accent2
                                font.pixelSize: 12
                                font.bold: true
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 8
                            Repeater {
                                model: root.bridge ? root.bridge.f0MonitorLevels : []
                                Rectangle {
                                    Layout.preferredWidth: 8
                                    Layout.preferredHeight: 12 + modelData * 54 + (root.bridge ? root.bridge.toneDeafRatio * 6 : 0)
                                    radius: 4
                                    color: index % 5 === 0 ? "#ff7fc0" : "#f269ad"
                                    opacity: 0.76 + Math.min(0.22, modelData * 0.22)
                                    Layout.alignment: Qt.AlignVCenter

                                    Behavior on Layout.preferredHeight {
                                        NumberAnimation { duration: 90; easing.type: Easing.OutCubic }
                                    }
                                }
                            }
                        }
                        Text {
                            text: root.bridge ? root.bridge.toneMonitorStatus : "请先导入或加载歌曲"
                            color: root.textMuted
                            font.pixelSize: 13
                            horizontalAlignment: Text.AlignHCenter
                            Layout.fillWidth: true
                        }
                    }
                }

                Text {
                    text: "DSP 实时声学参数"
                    color: root.textMuted
                    font.pixelSize: 15
                    font.bold: true
                    Layout.fillWidth: true
                }

                Text {
                    text: "分离与重组算法预设"
                    color: root.textMain
                    font.pixelSize: 14
                    Layout.fillWidth: true
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    radius: 8
                    color: "#151722"
                    border.color: "#262938"
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 4
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            radius: 6
                            color: root.bridge && root.bridge.rightPanelPresetIndex === 0 ? root.accent : "transparent"
                            Text {
                                anchors.centerIn: parent
                                text: "快速预览"
                                color: root.bridge && root.bridge.rightPanelPresetIndex === 0 ? "white" : root.textMuted
                                font.pixelSize: 14
                                font.bold: true
                            }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: if (root.bridge) root.bridge.setRightPanelPreset(0)
                            }
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            radius: 6
                            color: root.bridge && root.bridge.rightPanelPresetIndex === 1 ? root.accent : "transparent"
                            Text {
                                anchors.centerIn: parent
                                text: "真实分离"
                                color: root.bridge && root.bridge.rightPanelPresetIndex === 1 ? "white" : root.textMuted
                                font.pixelSize: 14
                                font.bold: root.bridge && root.bridge.rightPanelPresetIndex === 1
                            }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: if (root.bridge) root.bridge.setRightPanelPreset(1)
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 132
                    radius: 12
                    color: "#11141f"
                    border.color: "#272b3a"
                    RowLayout {
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.margins: 16
                        Text {
                            text: "AI 自动修补原唱"
                            color: root.textDim
                            font.pixelSize: 16
                            font.bold: true
                            Layout.fillWidth: true
                        }
                        Switch {
                            checked: true
                            enabled: false
                        }
                    }
                    Text {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.topMargin: 54
                        anchors.margins: 16
                        text: "实验功能暂未接入真实模型，当前不会影响播放或导出。后续确认可交付方案后再开放。"
                        color: root.textMuted
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                }

                Item { Layout.fillHeight: true }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "输出引擎:"
                            color: root.textMuted
                            font.pixelSize: 13
                            Layout.fillWidth: true
                        }
                        Text {
                            text: root.bridge ? root.bridge.outputEngineStatus : "未就绪"
                            color: root.accent2
                            font.pixelSize: 13
                            font.bold: true
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "对齐检测:"
                            color: root.textMuted
                            font.pixelSize: 13
                            Layout.fillWidth: true
                        }
                        Text {
                            text: root.bridge ? root.bridge.alignmentLatencyStatus : "未检测"
                            color: root.teal
                            font.pixelSize: 13
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "VST 状态:"
                            color: root.textMuted
                            font.pixelSize: 13
                            Layout.fillWidth: true
                        }
                        Text {
                            text: root.bridge ? root.bridge.masterPluginStatus : "未加载"
                            color: root.textMuted
                            font.pixelSize: 13
                            elide: Text.ElideRight
                            Layout.preferredWidth: 180
                            horizontalAlignment: Text.AlignRight
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "歌词引擎:"
                            color: root.textMuted
                            font.pixelSize: 13
                            Layout.fillWidth: true
                        }
                        Text {
                            text: root.bridge ? root.bridge.lyricsEngineStatus : "未选择"
                            color: root.textMuted
                            font.pixelSize: 13
                        }
                    }
                }
            }
        }

        Rectangle {
            id: centerPane
            anchors.left: leftPane.right
            anchors.right: rightPane.left
            anchors.top: topBar.bottom
            anchors.bottom: bottomBar.top
            color: "#07080d"

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 34
                anchors.rightMargin: 34
                anchors.topMargin: 34
                anchors.bottomMargin: 32
                spacing: 18

                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 50
                    Text {
                        text: "♬"
                        color: root.accent2
                        font.pixelSize: 27
                    }
                    Text {
                        text: "滚动歌词主舞台"
                        color: root.textMain
                        font.pixelSize: 24
                        font.bold: true
                    }
                    Text {
                        text: "（双击任意句进行智能改唱）"
                        color: root.accent2
                        font.pixelSize: 14
                        Layout.fillWidth: true
                    }
                    SecondaryButton {
                        text: root.bridge && root.bridge.lyricsGenerationBusy ? "生成中" : "生成歌词"
                        enabled: !(root.bridge && root.bridge.lyricsGenerationBusy)
                        Layout.preferredWidth: 112
                        Layout.preferredHeight: 36
                        onClicked: if (root.bridge) root.bridge.generateSmartLyrics()
                    }
                    Rectangle {
                        Layout.preferredWidth: 210
                        Layout.preferredHeight: 30
                        radius: 15
                        color: "#241020"
                        border.color: "#69254a"
                        Text {
                            anchors.centerIn: parent
                            text: songList.currentIndex >= 0 && root.bridge && root.bridge.songNames.length > 0 ? (root.bridge.songNames[songList.currentIndex] + " - LRC 同步中") : "LRC 同步中"
                            color: root.accent2
                            font.pixelSize: 13
                            elide: Text.ElideRight
                            width: parent.width - 22
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: "#151720"
                }

                Rectangle {
                    visible: root.bridge && root.bridge.lyricsGenerationBusy
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? 54 : 0
                    radius: 10
                    color: "#111520"
                    border.color: "#293146"
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16
                        anchors.rightMargin: 16
                        spacing: 12
                        Text {
                            text: root.bridge ? root.bridge.lyricsGenerationStatus : "正在生成歌词"
                            color: root.textMain
                            font.pixelSize: 14
                            Layout.preferredWidth: 190
                            elide: Text.ElideRight
                        }
                        ProgressBar {
                            from: 0
                            to: 100
                            value: root.bridge ? root.bridge.lyricsGenerationProgress : 0
                            indeterminate: root.bridge && root.bridge.lyricsGenerationBusy && root.bridge.lyricsGenerationProgress < 90
                            Layout.fillWidth: true
                        }
                        Text {
                            text: root.bridge ? (root.bridge.lyricsGenerationProgress + "%") : "0%"
                            color: root.accent2
                            font.pixelSize: 13
                            font.bold: true
                            Layout.preferredWidth: 46
                            horizontalAlignment: Text.AlignRight
                        }
                    }
                }

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    ListView {
                        id: lyricList
                        anchors.fill: parent
                        clip: true
                        model: root.bridge ? root.bridge.lyricLines : []
                        currentIndex: root.bridge ? root.bridge.currentLyricIndex : -1
                        preferredHighlightBegin: height * 0.48
                        preferredHighlightEnd: height * 0.58
                        highlightRangeMode: ListView.StrictlyEnforceRange
                        boundsBehavior: Flickable.StopAtBounds
                        spacing: 24
                        onCurrentIndexChanged: {
                            if (currentIndex >= 0)
                                positionViewAtIndex(currentIndex, ListView.Center)
                        }

                        delegate: Rectangle {
                            property bool active: ListView.isCurrentItem
                            property bool sung: root.bridge && root.bridge.currentLyricIndex >= 0 && index < root.bridge.currentLyricIndex

                            width: active ? Math.max(260, lyricList.width - 8) : (sung ? Math.min(430, lyricList.width * 0.54) : Math.min(520, Math.max(220, lyricText.implicitWidth + 72)))
                            height: active ? 62 : (sung ? 44 : 58)
                            x: (lyricList.width - width) / 2
                            radius: active ? 16 : 12
                            color: active ? "#2a0a1d" : "transparent"
                            border.color: active ? "#6a2149" : "transparent"
                            opacity: sung && !active ? 0.68 : 1.0

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: active ? 20 : 4
                                anchors.rightMargin: active ? 18 : 4
                                spacing: active ? 12 : 8

                                Text {
                                    id: lyricText
                                    text: root.lyricProgressHtml(modelData, root.bridge ? root.bridge.currentLyricProgress : 0, active, sung)
                                    textFormat: active ? Text.RichText : Text.PlainText
                                    color: active ? root.accent2 : (sung ? "#948696" : root.textMain)
                                    font.pixelSize: active ? 25 : (sung ? 15 : 20)
                                    font.bold: active || sung
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                    verticalAlignment: Text.AlignVCenter
                                }

                                Rectangle {
                                    id: lyricTimeBadge
                                    Layout.preferredWidth: 76
                                    Layout.preferredHeight: 28
                                    Layout.alignment: Qt.AlignVCenter | Qt.AlignRight
                                    radius: 15
                                    color: "#171a24"
                                    border.color: active ? "#3d325f" : "#262a38"
                                    visible: active
                                    Text {
                                        anchors.centerIn: parent
                                        text: root.bridge && root.bridge.lyricTimeLabels.length > index ? root.bridge.lyricTimeLabels[index] : "--:--"
                                        color: active ? "#d9d0ff" : root.accent2
                                        font.pixelSize: 13
                                        font.bold: true
                                        font.family: "Consolas"
                                    }
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                acceptedButtons: Qt.LeftButton
                                onClicked: lyricList.currentIndex = index
                                onDoubleClicked: {
                                    lyricList.currentIndex = index
                                    root.rewriteLyricIndex = index
                                    rewritePopup.originalLyric = modelData
                                    rewriteText.text = modelData
                                    rewritePopup.open()
                                }
                            }
                        }
                    }

                    Text {
                        anchors.centerIn: parent
                        visible: !root.bridge || root.bridge.lyricLines.length === 0
                        text: "纯音乐或暂无歌词"
                        color: root.textMuted
                        font.pixelSize: 24
                    }
                }

                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: Math.min(parent.width * 0.92, 760)
                    Layout.preferredHeight: 126
                    radius: 14
                    color: "#0f1119"
                    border.color: "#1f2433"
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 12
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "对齐校正"
                                color: root.textMain
                                font.pixelSize: 15
                                font.bold: true
                            }
                            Text {
                                text: root.bridge ? ("当前歌词偏移: " + root.bridge.lyricsOffsetLabel) : "当前歌词偏移: 0s"
                                color: root.textMuted
                                font.pixelSize: 13
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            MiniButton {
                                text: "-0.5s\n提前"
                                active: root.bridge && root.bridge.lyricsOffsetMs === -500
                                Layout.fillWidth: true
                                onClicked: if (root.bridge) root.bridge.setLyricsOffsetMs(-500)
                            }
                            MiniButton {
                                text: "-0.1s"
                                active: root.bridge && root.bridge.lyricsOffsetMs === -100
                                Layout.fillWidth: true
                                onClicked: if (root.bridge) root.bridge.setLyricsOffsetMs(-100)
                            }
                            MiniButton {
                                text: "0s\n不校正"
                                active: !root.bridge || root.bridge.lyricsOffsetMs === 0
                                Layout.fillWidth: true
                                onClicked: if (root.bridge) root.bridge.setLyricsOffsetMs(0)
                            }
                            MiniButton {
                                text: "+0.1s"
                                active: root.bridge && root.bridge.lyricsOffsetMs === 100
                                Layout.fillWidth: true
                                onClicked: if (root.bridge) root.bridge.setLyricsOffsetMs(100)
                            }
                            MiniButton {
                                text: "+0.5s\n延迟"
                                active: root.bridge && root.bridge.lyricsOffsetMs === 500
                                Layout.fillWidth: true
                                onClicked: if (root.bridge) root.bridge.setLyricsOffsetMs(500)
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            id: bottomBar
            height: 138
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            color: "#0b0c12"
            border.color: "#1b1d27"

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 24
                anchors.rightMargin: 24
                anchors.topMargin: 10
                anchors.bottomMargin: 16
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 14
                    Text {
                        text: root.bridge ? root.bridge.playbackTime.split(" / ")[0] : "00:00"
                        color: root.textMuted
                        font.pixelSize: 13
                        font.family: "Consolas"
                    }
                    Slider {
                        id: progressSlider
                        from: 0.0
                        to: 1.0
                        value: root.bridge ? root.bridge.playbackProgress : 0.0
                        Layout.fillWidth: true
                        onMoved: if (root.bridge) root.bridge.seekProgress(value)
                    }
                    Text {
                        text: root.bridge ? root.bridge.playbackTime.split(" / ")[1] : "00:00"
                        color: root.textMuted
                        font.pixelSize: 13
                        font.family: "Consolas"
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 18

                    IconButton {
                        label: "■"
                        tip: "停止"
                        onClicked: if (root.bridge) root.bridge.stop()
                    }

                    Rectangle {
                        Layout.preferredWidth: 60
                        Layout.preferredHeight: 60
                        radius: 16
                        color: root.accent
                        Text {
                            anchors.centerIn: parent
                            text: root.bridge && root.bridge.isPlaying ? "Ⅱ" : "▶"
                            color: "white"
                            font.pixelSize: 24
                            font.bold: true
                        }
                        MouseArea {
                            anchors.fill: parent
                            onClicked: if (root.bridge) root.bridge.isPlaying ? root.bridge.pause() : root.bridge.startAudioOutput()
                        }
                    }

                    IconButton {
                        label: root.bridge && root.bridge.playModeLabel === "单曲循环" ? "↻" : "⇥"
                        tip: root.bridge ? root.bridge.playModeLabel : "播放模式"
                        onClicked: if (root.bridge) root.bridge.cyclePlayMode()
                    }

                    Rectangle {
                        Layout.preferredWidth: 1
                        Layout.preferredHeight: 66
                        color: "#1e212c"
                    }

                    BottomSlider {
                        title: "人声音量"
                        valueText: Math.round(vocalGain.value * 100) + "%"
                        slider: vocalGain
                        muted: root.bridge ? root.bridge.vocalMuted : false
                        muteClicked: function() { if (root.bridge) root.bridge.toggleVocalMute() }
                        Layout.fillWidth: true
                    }

                    BottomSlider {
                        title: "伴奏音量"
                        valueText: Math.round(instGain.value * 100) + "%"
                        slider: instGain
                        muted: root.bridge ? root.bridge.instrumentalMuted : false
                        muteClicked: function() { if (root.bridge) root.bridge.toggleInstrumentalMute() }
                        Layout.fillWidth: true
                    }

                    BottomSlider {
                        title: "主输出增益"
                        valueText: masterSlider.value.toFixed(1) + "dB"
                        slider: masterSlider
                        muted: false
                        muteClicked: function() {}
                        Layout.fillWidth: true
                    }

                    Rectangle {
                        Layout.preferredWidth: 1
                        Layout.preferredHeight: 66
                        color: "#1e212c"
                    }

                    SecondaryButton {
                        text: "VST 宿主"
                        Layout.preferredWidth: 132
                        onClicked: vstPluginDialog.open()
                    }

                    Rectangle {
                        Layout.preferredWidth: 240
                        Layout.preferredHeight: 58
                        radius: 10
                        color: "#151722"
                        border.color: "#242839"
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 14
                            anchors.rightMargin: 14
                            anchors.topMargin: 8
                            anchors.bottomMargin: 8
                            spacing: 4
                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    text: "跑调破坏度 (F0)"
                                    color: root.accent2
                                    font.pixelSize: 13
                                    font.bold: true
                                    Layout.fillWidth: true
                                }
                                Text {
                                    text: root.bridge ? (Math.round(root.bridge.toneDeafRatio * 100) + "%") : "0%"
                                    color: root.accent2
                                    font.pixelSize: 13
                                    font.bold: true
                                }
                            }
                            Slider {
                                id: toneVisualSlider
                                from: 0.0
                                to: 1.0
                                value: root.tonePreviewValue
                                Layout.fillWidth: true
                                onMoved: {
                                    root.tonePreviewValue = value
                                    if (!toneApplyTimer.running)
                                        toneApplyTimer.start()
                                }
                                onPressedChanged: {
                                    if (!pressed) {
                                        toneApplyTimer.stop()
                                        toneSlider.value = root.tonePreviewValue
                                        if (root.bridge)
                                            root.bridge.setToneDeafRatio(root.tonePreviewValue)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Slider {
                id: toneSlider
                visible: false
                from: 0.0
                to: 1.0
                value: 0.4
                onValueChanged: root.tonePreviewValue = value
            }

            Slider {
                id: vocalGain
                visible: false
                from: 0.0
                to: 1.5
                value: 1.0
                onValueChanged: if (root.bridge) root.bridge.setTrackGains(value, instGain.value)
            }

            Slider {
                id: instGain
                visible: false
                from: 0.0
                to: 1.5
                value: 0.8
                onValueChanged: if (root.bridge) root.bridge.setTrackGains(vocalGain.value, value)
            }

            Slider {
                id: masterSlider
                visible: false
                from: -12.0
                to: 3.0
                value: -3.0
            }
        }
    }

    component IconButton: Button {
        property string label: ""
        property string tip: ""
        text: label
        ToolTip.text: tip
        ToolTip.visible: hovered && tip.length > 0
        Layout.preferredWidth: 52
        Layout.preferredHeight: 52
        contentItem: Text {
            text: parent.text
            color: parent.enabled ? root.textMain : root.textDim
            font.pixelSize: 20
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 10
            color: parent.down ? "#242633" : "#14161f"
            border.color: "#252936"
        }
    }

    component PrimaryButton: Button {
        Layout.preferredHeight: 52
        contentItem: Text {
            text: parent.text
            color: "white"
            font.pixelSize: 15
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: 8
            color: parent.enabled ? (parent.down ? "#bf1d6d" : root.accent) : "#33313a"
        }
    }

    component SecondaryButton: Button {
        Layout.preferredHeight: 44
        contentItem: Text {
            text: parent.text
            color: parent.enabled ? root.textMain : root.textDim
            font.pixelSize: 14
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: 7
            color: parent.down ? "#1c1f2b" : "#141720"
            border.color: "#272b39"
        }
    }

    component MiniButton: Button {
        property bool active: false
        Layout.preferredWidth: 86
        Layout.minimumWidth: 70
        Layout.preferredHeight: 60
        contentItem: Text {
            text: parent.text
            color: parent.active ? root.accent2 : root.textMain
            font.pixelSize: 15
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.WordWrap
        }
        background: Rectangle {
            radius: 8
            color: parent.active ? "#2a0f23" : "#151721"
            border.color: parent.active ? "#6d214b" : "#272b39"
        }
    }

    component SettingsLabel: Text {
        color: root.textMain
        font.pixelSize: 14
        font.bold: true
        Layout.topMargin: 6
        Layout.fillWidth: true
    }

    component BottomSlider: RowLayout {
        property string title: ""
        property string valueText: ""
        property Slider slider
        property bool muted: false
        property var muteClicked
        spacing: 10
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: title
                    color: root.accent2
                    font.pixelSize: 13
                    font.bold: true
                    Layout.fillWidth: true
                }
                Text {
                    text: valueText
                    color: root.textMuted
                    font.pixelSize: 12
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Rectangle {
                    Layout.preferredWidth: 34
                    Layout.preferredHeight: 34
                    radius: 6
                    color: muted ? "#2a0f23" : "#161925"
                    border.color: "#222638"
                    Text {
                        anchors.centerIn: parent
                        text: muted ? "已静" : "静"
                        color: muted ? root.accent2 : root.textMain
                        font.bold: true
                        font.pixelSize: 13
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: muteClicked()
                    }
                }
                Slider {
                    Layout.fillWidth: true
                    from: slider ? slider.from : 0
                    to: slider ? slider.to : 1
                    value: slider ? slider.value : 0
                    onMoved: if (slider) slider.value = value
                }
            }
        }
    }
}
