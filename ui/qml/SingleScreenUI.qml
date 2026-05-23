import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1280
    height: 720
    minimumWidth: 1040
    minimumHeight: 640
    visible: true
    title: "Audio Forge"
    color: "#101114"
    property var bridge: audioWorkbench
    property string fileTarget: "vocal"

    FileDialog {
        id: inputDialog
        title: "Select audio or lyrics file"
        onAccepted: if (root.bridge) root.bridge.setPathFromUrl(root.fileTarget, selectedFile.toString())
    }

    FileDialog {
        id: songImportDialog
        title: "Import complete song"
        nameFilters: ["Audio files (*.wav *.mp3 *.flac *.ogg *.m4a *.aac)", "All files (*)"]
        onAccepted: if (root.bridge) root.bridge.importSongWithBackends(selectedFile.toString(), separatorPicker.currentText, lyricsBackendPicker.currentText)
    }

    FileDialog {
        id: outputDialog
        title: "Select output wav"
        fileMode: FileDialog.SaveFile
        nameFilters: ["Wave files (*.wav)"]
        onAccepted: if (root.bridge) root.bridge.setPathFromUrl("output", selectedFile.toString())
    }

    FolderDialog {
        id: songsFolderDialog
        title: "Select songs folder"
        onAccepted: if (root.bridge) root.bridge.setSongsRootFromUrl(selectedFolder.toString())
    }

    Rectangle {
        anchors.fill: parent
        color: "#101114"

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 28
            spacing: 18

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 64

                Label {
                    text: "Audio Forge"
                    color: "#f5f1e8"
                    font.pixelSize: 34
                    font.bold: true
                    Layout.fillWidth: true
                }

                Label {
                    text: root.bridge ? root.bridge.status : ""
                    color: "#a9b7a2"
                    elide: Text.ElideMiddle
                    horizontalAlignment: Text.AlignRight
                    Layout.preferredWidth: 560
                }
            }

            GridLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                columns: 2
                rowSpacing: 18
                columnSpacing: 18

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 8
                    color: "#191b20"
                    border.color: "#2b3036"

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 22
                        spacing: 14

                        Label {
                            text: "Stems"
                            color: "#f5f1e8"
                            font.pixelSize: 18
                            font.bold: true
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            TextField {
                                text: root.bridge ? root.bridge.songsRoot : ""
                                placeholderText: "Songs folder"
                                color: "#f5f1e8"
                                selectionColor: "#477d7d"
                                selectedTextColor: "#ffffff"
                                Layout.fillWidth: true
                                onEditingFinished: if (root.bridge) root.bridge.songsRoot = text
                            }

                            Button {
                                text: "..."
                                Layout.preferredWidth: 42
                                onClicked: songsFolderDialog.open()
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            ComboBox {
                                id: songPicker
                                model: root.bridge ? root.bridge.songNames : []
                                Layout.fillWidth: true
                            }

                            Button {
                                text: "Scan"
                                Layout.preferredWidth: 72
                                onClicked: if (root.bridge) root.bridge.scanSongs()
                            }

                            Button {
                                text: "Use"
                                Layout.preferredWidth: 64
                                onClicked: if (root.bridge) root.bridge.loadSongAt(songPicker.currentIndex)
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            ComboBox {
                                id: separatorPicker
                                model: root.bridge ? root.bridge.separatorBackends : []
                                currentIndex: 0
                                Layout.fillWidth: true
                                onActivated: if (root.bridge) root.bridge.setSeparatorBackend(currentText)
                            }

                            ComboBox {
                                id: lyricsBackendPicker
                                model: root.bridge ? root.bridge.lyricsBackends : []
                                currentIndex: 0
                                Layout.fillWidth: true
                                onActivated: if (root.bridge) root.bridge.setLyricsBackend(currentText)
                            }
                        }

                        PathPicker {
                            text: root.bridge ? root.bridge.vocalPath : ""
                            placeholderText: "Vocal wav"
                            onTextEdited: if (root.bridge) root.bridge.vocalPath = text
                            onPick: {
                                root.fileTarget = "vocal"
                                inputDialog.nameFilters = ["Audio files (*.wav *.flac *.ogg *.aiff)", "All files (*)"]
                                inputDialog.open()
                            }
                        }

                        PathPicker {
                            text: root.bridge ? root.bridge.instrumentalPath : ""
                            placeholderText: "Instrumental wav"
                            onTextEdited: if (root.bridge) root.bridge.instrumentalPath = text
                            onPick: {
                                root.fileTarget = "instrumental"
                                inputDialog.nameFilters = ["Audio files (*.wav *.flac *.ogg *.aiff)", "All files (*)"]
                                inputDialog.open()
                            }
                        }

                        PathPicker {
                            text: root.bridge ? root.bridge.outputPath : ""
                            placeholderText: "Output wav"
                            onTextEdited: if (root.bridge) root.bridge.outputPath = text
                            onPick: outputDialog.open()
                        }

                        PathPicker {
                            text: root.bridge ? root.bridge.lyricsPath : ""
                            placeholderText: "Lyrics lrc/srt"
                            onTextEdited: if (root.bridge) root.bridge.lyricsPath = text
                            onPick: {
                                root.fileTarget = "lyrics"
                                inputDialog.nameFilters = ["Lyrics files (*.lrc *.srt)", "All files (*)"]
                                inputDialog.open()
                            }
                        }

                        Item {
                            Layout.fillHeight: true
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            Button {
                                text: "Mock"
                                Layout.preferredWidth: 112
                                Layout.preferredHeight: 42
                                onClicked: if (root.bridge) root.bridge.generateMockAudio()
                            }

                            Button {
                                text: "Load"
                                Layout.preferredWidth: 112
                                Layout.preferredHeight: 42
                                onClicked: if (root.bridge) root.bridge.loadPlayback()
                            }

                            Button {
                                text: "Import Song"
                                Layout.preferredWidth: 132
                                Layout.preferredHeight: 42
                                onClicked: songImportDialog.open()
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 8
                    color: "#171c1d"
                    border.color: "#2e3b3b"

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 22
                        spacing: 16

                        Label {
                            text: "Render"
                            color: "#f5f1e8"
                            font.pixelSize: 18
                            font.bold: true
                        }

                        Label {
                            text: "Tone drift " + Math.round(toneSlider.value * 100) + "%"
                            color: "#d9e2d0"
                            font.pixelSize: 14
                        }

                        Slider {
                            id: toneSlider
                            from: 0.0
                            to: 1.0
                            value: 0.4
                            stepSize: 0.05
                            Layout.fillWidth: true
                        }

                        Label {
                            text: "Master " + masterSlider.value.toFixed(1) + " dB"
                            color: "#d9e2d0"
                            font.pixelSize: 14
                        }

                        Slider {
                            id: masterSlider
                            from: -12.0
                            to: 3.0
                            value: -3.0
                            stepSize: 0.5
                            Layout.fillWidth: true
                        }

                        Label {
                            text: "Vocal " + vocalGain.value.toFixed(2) + "  Inst " + instGain.value.toFixed(2)
                            color: "#d9e2d0"
                            font.pixelSize: 14
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            Slider {
                                id: vocalGain
                                from: 0.0
                                to: 1.5
                                value: 1.0
                                stepSize: 0.05
                                Layout.fillWidth: true
                                onMoved: if (root.bridge) root.bridge.setTrackGains(value, instGain.value)
                            }

                            Slider {
                                id: instGain
                                from: 0.0
                                to: 1.5
                                value: 1.0
                                stepSize: 0.05
                                Layout.fillWidth: true
                                onMoved: if (root.bridge) root.bridge.setTrackGains(vocalGain.value, value)
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            ComboBox {
                                id: audioDevicePicker
                                model: root.bridge ? root.bridge.audioDeviceNames : []
                                currentIndex: root.bridge ? root.bridge.selectedAudioDeviceIndex : -1
                                Layout.fillWidth: true
                                onActivated: if (root.bridge) root.bridge.selectAudioDevice(index)
                            }

                            Button {
                                text: "Devices"
                                Layout.preferredWidth: 92
                                onClicked: if (root.bridge) root.bridge.refreshAudioDevices()
                            }
                        }

                        Label {
                            text: root.bridge ? root.bridge.currentLyric : ""
                            color: "#f5f1e8"
                            font.pixelSize: 24
                            font.bold: true
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }

                        Label {
                            text: root.bridge ? root.bridge.nextLyric : ""
                            color: "#9da8a0"
                            font.pixelSize: 14
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }

                        Slider {
                            id: progressSlider
                            from: 0.0
                            to: 1.0
                            value: root.bridge ? root.bridge.playbackProgress : 0.0
                            Layout.fillWidth: true
                            onMoved: if (root.bridge) root.bridge.seekProgress(value)
                        }

                        Label {
                            text: root.bridge ? root.bridge.playbackTime : "00:00 / 00:00"
                            color: "#d9e2d0"
                            font.pixelSize: 13
                        }

                        Item {
                            Layout.fillHeight: true
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            Button {
                                text: root.bridge && root.bridge.isPlaying ? "Pause" : "Play"
                                Layout.preferredWidth: 108
                                Layout.preferredHeight: 44
                                onClicked: if (root.bridge) root.bridge.isPlaying ? root.bridge.pause() : root.bridge.play()
                            }

                            Button {
                                text: root.bridge && root.bridge.audioOutputActive ? "Audio Off" : "Audio"
                                Layout.preferredWidth: 108
                                Layout.preferredHeight: 44
                                onClicked: if (root.bridge) root.bridge.audioOutputActive ? root.bridge.stopAudioOutput() : root.bridge.startAudioOutput()
                            }

                            Button {
                                text: "Stop"
                                Layout.preferredWidth: 96
                                Layout.preferredHeight: 44
                                onClicked: if (root.bridge) root.bridge.stop()
                            }

                            Button {
                                text: "Export"
                                Layout.preferredWidth: 108
                                Layout.preferredHeight: 44
                                onClicked: if (root.bridge) root.bridge.exportMix(toneSlider.value, masterSlider.value)
                            }

                            Button {
                                text: "Check"
                                Layout.preferredWidth: 108
                                Layout.preferredHeight: 44
                                onClicked: if (root.bridge) root.bridge.evaluateAlignment()
                            }
                        }
                    }
                }
            }
        }
    }

    component PathPicker: RowLayout {
        property alias text: field.text
        property alias placeholderText: field.placeholderText
        signal textEdited()
        signal pick()

        Layout.fillWidth: true
        spacing: 8

        TextField {
            id: field
            color: "#f5f1e8"
            selectionColor: "#477d7d"
            selectedTextColor: "#ffffff"
            Layout.fillWidth: true
            onEditingFinished: parent.textEdited()
        }

        Button {
            text: "..."
            Layout.preferredWidth: 42
            onClicked: parent.pick()
        }
    }
}
