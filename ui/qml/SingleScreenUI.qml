import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1280
    height: 720
    minimumWidth: 1080
    minimumHeight: 640
    visible: true
    title: "AI主播演唱助手 - 真人唱功模拟"
    color: "#100817"

    property var bridge: audioWorkbench
    property string fileTarget: "vocal"
    property color bg: "#100817"
    property color panel: "#181322"
    property color panelSoft: "#211a2c"
    property color panelLine: "#322842"
    property color accent: "#f04474"
    property color accentSoft: "#3b1828"
    property color textMain: "#f5edf4"
    property color textMuted: "#a89bad"
    property color gold: "#f4bd62"

    function selectedSeparatorBackend() {
        if (!root.bridge || separatorPicker.currentIndex < 0)
            return "preview"
        return root.bridge.separatorBackends[separatorPicker.currentIndex]
    }

    function selectedLyricsBackend() {
        if (!root.bridge || lyricsBackendPicker.currentIndex < 0)
            return "preview"
        return root.bridge.lyricsBackends[lyricsBackendPicker.currentIndex]
    }

    Component.onCompleted: if (root.bridge) root.bridge.refreshAudioDevices()

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
        title: "选择导出 wav"
        fileMode: FileDialog.SaveFile
        nameFilters: ["Wave 文件 (*.wav)"]
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
        width: Math.min(parent.width * 0.72, 760)
        modal: false
        focus: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 18

        background: Rectangle {
            radius: 8
            color: "#24152a"
            border.color: root.accent
            opacity: 0.96
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

    Timer {
        id: statusPopupTimer
        interval: 3600
        repeat: false
        onTriggered: statusPopup.close()
    }

    Connections {
        target: root.bridge
        function onStatusChanged() {
            if (!root.bridge || root.bridge.status === "" || root.bridge.status === "Ready")
                return
            statusPopup.open()
            statusPopupTimer.restart()
        }
    }

    Rectangle {
        anchors.fill: parent
        color: root.bg

        Rectangle {
            id: titleBar
            height: 30
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            color: "#5a4a86"

            Text {
                anchors.left: parent.left
                anchors.leftMargin: 14
                anchors.verticalCenter: parent.verticalCenter
                text: "AI主播演唱助手 - 真人唱功模拟"
                color: "#f5f1ff"
                font.pixelSize: 13
                font.bold: true
            }
        }

        RowLayout {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: titleBar.bottom
            anchors.bottom: controlDeck.top
            anchors.margins: 16
            spacing: 18

            Rectangle {
                Layout.preferredWidth: 330
                Layout.fillHeight: true
                radius: 8
                color: root.panel
                border.color: root.panelLine

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 12

                    Text {
                        text: "歌曲库"
                        color: root.accent
                        font.pixelSize: 23
                        font.bold: true
                    }

                    TextField {
                        enabled: false
                        Layout.fillWidth: true
                        placeholderText: "搜索歌曲..."
                        text: ""
                        color: root.textMain
                        placeholderTextColor: "#6f6378"
                        background: Rectangle {
                            radius: 6
                            color: "#211a28"
                            border.color: "#383040"
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: 6
                        color: "#15111e"
                        border.color: "#30283a"
                        clip: true

                        ListView {
                            id: songList
                            anchors.fill: parent
                            model: root.bridge ? root.bridge.songNames : []
                            currentIndex: 0
                            delegate: Rectangle {
                                width: songList.width
                                height: 46
                                color: ListView.isCurrentItem ? root.accent : "transparent"

                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 14
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData
                                    color: ListView.isCurrentItem ? "#1b1018" : root.textMain
                                    font.pixelSize: 15
                                    elide: Text.ElideRight
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: songList.currentIndex = index
                                    onDoubleClicked: if (root.bridge) root.bridge.loadSongAt(index)
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Button {
                            text: "选择目录"
                            Layout.fillWidth: true
                            onClicked: songsFolderDialog.open()
                        }

                        Button {
                            text: "扫描"
                            Layout.preferredWidth: 78
                            onClicked: if (root.bridge) root.bridge.scanSongs()
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Button {
                            text: "加载选中"
                            Layout.fillWidth: true
                            onClicked: if (root.bridge) root.bridge.loadSongAt(songList.currentIndex)
                        }

                        Button {
                            text: root.bridge && root.bridge.importBusy ? "导入中" : "导入歌曲"
                            enabled: !(root.bridge && root.bridge.importBusy)
                            Layout.fillWidth: true
                            onClicked: songImportDialog.open()
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Button {
                            text: "删除选中"
                            enabled: !(root.bridge && root.bridge.importBusy)
                            Layout.fillWidth: true
                            onClicked: if (root.bridge) root.bridge.deleteSongAt(songList.currentIndex)
                        }

                        Button {
                            text: "清空列表"
                            enabled: !(root.bridge && root.bridge.importBusy)
                            Layout.fillWidth: true
                            onClicked: if (root.bridge) root.bridge.clearSongList()
                        }
                    }

                    Button {
                        text: "导入歌词文件"
                        Layout.fillWidth: true
                        onClicked: {
                            root.fileTarget = "lyrics"
                            inputDialog.nameFilters = ["歌词文件 (*.lrc *.srt)", "所有文件 (*)"]
                            inputDialog.open()
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 8
                color: "#0f0715"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 4

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 42

                        Text {
                            text: "滚动歌词"
                            color: root.textMain
                            font.pixelSize: 20
                            font.bold: true
                            Layout.fillWidth: true
                        }

                        Text {
                            text: root.bridge ? root.bridge.status : ""
                            color: root.textMuted
                            font.pixelSize: 12
                            elide: Text.ElideMiddle
                            horizontalAlignment: Text.AlignRight
                            Layout.preferredWidth: 430
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
                            preferredHighlightBegin: height * 0.42
                            preferredHighlightEnd: height * 0.58
                            highlightRangeMode: ListView.StrictlyEnforceRange
                            boundsBehavior: Flickable.StopAtBounds
                            spacing: 8

                            delegate: Rectangle {
                                property bool sung: root.bridge && root.bridge.currentLyricIndex >= 0 && index < root.bridge.currentLyricIndex

                                width: lyricList.width
                                height: ListView.isCurrentItem ? 72 : (sung ? 56 : 42)
                                radius: 10
                                color: ListView.isCurrentItem ? root.accentSoft : (sung ? "#1b1322" : "transparent")
                                opacity: ListView.isCurrentItem ? 0.96 : (sung ? 0.9 : 1.0)

                                Text {
                                    anchors.centerIn: parent
                                    width: parent.width - 48
                                    text: modelData
                                    color: ListView.isCurrentItem ? root.accent : (parent.sung ? "#d8bfd2" : root.textMuted)
                                    font.pixelSize: ListView.isCurrentItem ? 30 : (parent.sung ? 25 : 20)
                                    font.bold: ListView.isCurrentItem || parent.sung
                                    horizontalAlignment: Text.AlignHCenter
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        Text {
                            anchors.centerIn: parent
                            visible: !root.bridge || root.bridge.lyricLines.length === 0
                            text: "纯音乐或暂无歌词：可导入同名 .lrc/.srt，或点“生成歌词”。本地识别需要先安装 faster-whisper。"
                            color: root.textMuted
                            font.pixelSize: 18
                            width: parent.width * 0.86
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }

        Rectangle {
            id: controlDeck
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 318
            color: "#171020"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    Text {
                        text: root.bridge ? root.bridge.playbackTime : "00:00 / 00:00"
                        color: root.accent
                        font.pixelSize: 16
                        font.bold: true
                        Layout.preferredWidth: 138
                    }

                    Slider {
                        id: progressSlider
                        from: 0.0
                        to: 1.0
                        value: root.bridge ? root.bridge.playbackProgress : 0.0
                        Layout.fillWidth: true
                        onMoved: if (root.bridge) root.bridge.seekProgress(value)
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 18

                    Button {
                        text: root.bridge && root.bridge.isPlaying ? "暂停" : "播放"
                        enabled: !(root.bridge && root.bridge.importBusy)
                        Layout.preferredWidth: 110
                        Layout.preferredHeight: 44
                        onClicked: if (root.bridge) root.bridge.isPlaying ? root.bridge.pause() : root.bridge.startAudioOutput()
                    }

                    Button {
                        text: root.bridge && root.bridge.audioOutputActive ? "关闭音频" : "无声预览"
                        enabled: !(root.bridge && root.bridge.importBusy)
                        Layout.preferredWidth: 120
                        Layout.preferredHeight: 44
                        onClicked: if (root.bridge) root.bridge.audioOutputActive ? root.bridge.stopAudioOutput() : root.bridge.play()
                    }

                    Button {
                        text: "停止"
                        enabled: !(root.bridge && root.bridge.importBusy)
                        Layout.preferredWidth: 92
                        Layout.preferredHeight: 44
                        onClicked: if (root.bridge) root.bridge.stop()
                    }

                    Button {
                        text: root.bridge && root.bridge.vocalMuted ? "恢复人声" : "人声静音"
                        enabled: !(root.bridge && root.bridge.importBusy)
                        Layout.preferredWidth: 118
                        Layout.preferredHeight: 44
                        onClicked: if (root.bridge) root.bridge.toggleVocalMute()
                    }

                    Button {
                        text: root.bridge && root.bridge.instrumentalMuted ? "恢复伴奏" : "伴奏静音"
                        enabled: !(root.bridge && root.bridge.importBusy)
                        Layout.preferredWidth: 118
                        Layout.preferredHeight: 44
                        onClicked: if (root.bridge) root.bridge.toggleInstrumentalMute()
                    }

                    Button {
                        text: "真人唱功：关"
                        enabled: false
                        Layout.preferredWidth: 138
                        Layout.preferredHeight: 44
                    }

                    Item { Layout.fillWidth: true }

                    Button {
                        text: "生成样例"
                        enabled: !(root.bridge && root.bridge.importBusy)
                        Layout.preferredWidth: 86
                        onClicked: if (root.bridge) root.bridge.generateMockAudio()
                    }

                    Button {
                        text: "生成歌词"
                        enabled: !(root.bridge && root.bridge.importBusy)
                        Layout.preferredWidth: 96
                        onClicked: if (root.bridge) root.bridge.generateLyrics()
                    }

                    Button {
                        text: "加载"
                        enabled: !(root.bridge && root.bridge.importBusy)
                        Layout.preferredWidth: 86
                        onClicked: if (root.bridge) root.bridge.loadPlayback()
                    }

                    Button {
                        text: "导出"
                        enabled: !(root.bridge && root.bridge.importBusy)
                        Layout.preferredWidth: 86
                        onClicked: if (root.bridge) root.bridge.exportMix(toneSlider.value, masterSlider.value)
                    }

                    Button {
                        text: "检测"
                        enabled: !(root.bridge && root.bridge.importBusy)
                        Layout.preferredWidth: 86
                        onClicked: if (root.bridge) root.bridge.evaluateAlignment()
                    }
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: 3
                    rowSpacing: 16
                    columnSpacing: 26

                    DisabledControlRow {
                        title: "歌词字体"
                        valueText: "22px"
                        Layout.fillWidth: true
                    }

                    DisabledControlRow {
                        title: "歌词偏移"
                        valueText: "2.2秒"
                        Layout.fillWidth: true
                    }

                    SliderControlRow {
                        title: "跑调强度"
                        slider: toneSlider
                        from: 0.0
                        to: 1.0
                        decimals: 0
                        suffix: "%"
                        multiplier: 100
                        Layout.fillWidth: true
                    }

                    SliderControlRow {
                        title: "人声"
                        slider: vocalGain
                        from: 0.0
                        to: 1.5
                        decimals: 0
                        suffix: "%"
                        multiplier: 100
                        Layout.fillWidth: true
                    }

                    SliderControlRow {
                        title: "伴奏"
                        slider: instGain
                        from: 0.0
                        to: 1.5
                        decimals: 0
                        suffix: "%"
                        multiplier: 100
                        Layout.fillWidth: true
                    }

                    SliderControlRow {
                        title: "主输出"
                        slider: masterSlider
                        from: -12.0
                        to: 3.0
                        decimals: 1
                        suffix: " dB"
                        Layout.fillWidth: true
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Text {
                        text: "分离后端"
                        color: root.textMuted
                        font.pixelSize: 13
                    }

                    ComboBox {
                        id: separatorPicker
                        model: root.bridge ? root.bridge.separatorBackendLabels : []
                        currentIndex: 0
                        Layout.preferredWidth: 158
                        onActivated: if (root.bridge) root.bridge.setSeparatorBackend(root.selectedSeparatorBackend())
                    }

                    Text {
                        text: "歌词后端"
                        color: root.textMuted
                        font.pixelSize: 13
                    }

                    ComboBox {
                        id: lyricsBackendPicker
                        model: root.bridge ? root.bridge.lyricsBackendLabels : []
                        currentIndex: 0
                        Layout.preferredWidth: 150
                        onActivated: if (root.bridge) root.bridge.setLyricsBackend(root.selectedLyricsBackend())
                    }

                    Text {
                        text: root.bridge ? root.bridge.lyricsBackendStatus : ""
                        color: root.gold
                        font.pixelSize: 12
                        elide: Text.ElideRight
                        Layout.preferredWidth: 330
                    }

                    Text {
                        text: "输出设备"
                        color: root.textMuted
                        font.pixelSize: 13
                    }

                    ComboBox {
                        id: audioDevicePicker
                        model: root.bridge ? root.bridge.audioDeviceNames : []
                        currentIndex: root.bridge ? root.bridge.selectedAudioDeviceIndex : -1
                        Layout.fillWidth: true
                        onActivated: if (root.bridge) root.bridge.selectAudioDevice(index)
                    }

                    Button {
                        text: "刷新设备"
                        Layout.preferredWidth: 100
                        onClicked: if (root.bridge) root.bridge.refreshAudioDevices()
                    }

                    Button {
                        text: "选择导出"
                        Layout.preferredWidth: 100
                        onClicked: outputDialog.open()
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Text {
                        text: "主输出 VST"
                        color: root.textMuted
                        font.pixelSize: 13
                    }

                    Text {
                        text: root.bridge && root.bridge.masterPluginPath ? root.bridge.masterPluginPath : "未加载；加载后仅在“导出”时生效"
                        color: root.textMain
                        font.pixelSize: 13
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }

                    Button {
                        text: "加载 VST"
                        enabled: !(root.bridge && root.bridge.importBusy)
                        Layout.preferredWidth: 100
                        onClicked: vstPluginDialog.open()
                    }

                    Button {
                        text: "移除"
                        enabled: root.bridge && root.bridge.masterPluginPath && !(root.bridge && root.bridge.importBusy)
                        Layout.preferredWidth: 72
                        onClicked: if (root.bridge) root.bridge.clearMasterPlugin()
                    }
                }

                Text {
                    text: root.bridge ? ("状态：" + root.bridge.status) : ""
                    color: root.gold
                    font.pixelSize: 13
                    elide: Text.ElideMiddle
                    Layout.fillWidth: true
                }

                Text {
                    text: "使用提示：播放中拖动跑调强度会立刻换成新效果，长歌曲可能需要等几秒。要自动歌词，请先选歌词方式再点“生成歌词”。"
                    color: root.textMuted
                    font.pixelSize: 12
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }

            Slider {
                id: toneSlider
                visible: false
                from: 0.0
                to: 1.0
                value: 0.4
                onValueChanged: if (root.bridge) root.bridge.setToneDeafRatio(value)
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
                value: 1.0
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

    component LyricLine: Text {
        property bool muted: false
        property int size: 20
        width: parent ? parent.width : 800
        color: muted ? root.textMuted : root.textMain
        font.pixelSize: size
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
    }

    component SliderControlRow: RowLayout {
        property string title: ""
        property Slider slider
        property real from: 0.0
        property real to: 1.0
        property int decimals: 0
        property real multiplier: 1.0
        property string suffix: ""

        function valueText() {
            var shown = slider ? slider.value * multiplier : 0
            return shown.toFixed(decimals) + suffix
        }

        spacing: 10

        Text {
            text: title
            color: root.textMain
            font.pixelSize: 14
            Layout.preferredWidth: 82
        }

        Slider {
            id: visualSlider
            Layout.fillWidth: true
            Layout.preferredHeight: 22
            from: parent.from
            to: parent.to
            value: parent.slider ? parent.slider.value : parent.from
            onMoved: if (parent.slider) parent.slider.value = value

            background: Rectangle {
                x: visualSlider.leftPadding
                y: visualSlider.topPadding + visualSlider.availableHeight / 2 - height / 2
                width: visualSlider.availableWidth
                height: 6
                radius: 3
                color: "#332b3a"

                Rectangle {
                    width: visualSlider.visualPosition * parent.width
                    height: parent.height
                    radius: 3
                    color: root.accent
                }
            }

            handle: Rectangle {
                x: visualSlider.leftPadding + visualSlider.visualPosition * (visualSlider.availableWidth - width)
                y: visualSlider.topPadding + visualSlider.availableHeight / 2 - height / 2
                width: 16
                height: 16
                radius: 8
                color: "#f8d7e1"
                border.color: root.accent
            }
        }

        Text {
            text: valueText()
            color: root.accent
            font.pixelSize: 14
            horizontalAlignment: Text.AlignRight
            Layout.preferredWidth: 54
        }
    }

    component DisabledControlRow: RowLayout {
        property string title: ""
        property string valueText: ""

        spacing: 10

        Text {
            text: title
            color: "#665d6a"
            font.pixelSize: 14
            Layout.preferredWidth: 82
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 6
            radius: 3
            color: "#2a2530"

            Rectangle {
                width: parent.width * 0.38
                height: parent.height
                radius: 3
                color: "#5d5663"
            }
        }

        Text {
            text: valueText
            color: "#766d79"
            font.pixelSize: 14
            horizontalAlignment: Text.AlignRight
            Layout.preferredWidth: 54
        }
    }
}
