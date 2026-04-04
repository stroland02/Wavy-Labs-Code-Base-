import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    color: theme.bg

    readonly property color surface: theme.surface
    readonly property color accent:  theme.accent
    readonly property color text_:   theme.fg
    readonly property color dim:     theme.dim
    readonly property color border_: theme.outline

    // Parse a log line's tag prefix
    function lineTag(txt) {
        if (txt.startsWith("[WARN]"))  return "WARN"
        if (txt.startsWith("[ERROR]")) return "ERROR"
        if (txt.startsWith("[INFO]"))  return "INFO"
        if (txt.startsWith("[AI]"))    return "AI"
        return ""
    }
    function lineColor(tag) {
        if (tag === "WARN")  return "#ffd600"
        if (tag === "ERROR") return "#ef5350"
        if (tag === "INFO")  return Qt.rgba(accent.r, accent.g, accent.b, 1)
        if (tag === "AI")    return "#81c784"
        return "#a0d0a0"
    }
    function lineBody(txt, tag) {
        if (tag === "WARN"  && txt.length > 7)  return txt.substring(7)
        if (tag === "ERROR" && txt.length > 8)  return txt.substring(8)
        if (tag === "INFO"  && txt.length > 7)  return txt.substring(7)
        if (tag === "AI"    && txt.length > 5)  return txt.substring(5)
        return txt
    }

    // Line model — appends incrementally on log change
    ListModel { id: consoleModel }
    property int _lastLineCount: 0

    function _rebuildModel() {
        consoleModel.clear()
        _lastLineCount = 0
        _appendNewLines()
    }

    function _appendNewLines() {
        var lines = backend.consoleLog.split("\n")
        // Detect clear (new count < tracked count) → full rebuild
        if (lines.length < _lastLineCount) {
            consoleModel.clear()
            _lastLineCount = 0
        }
        for (var i = _lastLineCount; i < lines.length; i++) {
            if (lines[i].length > 0)
                consoleModel.append({ lineText: lines[i] })
        }
        _lastLineCount = lines.length
    }

    Connections {
        target: backend
        function onConsoleLogChanged() { root._appendNewLines() }
    }

    Component.onCompleted: {
        if (backend.consoleLog.length > 0)
            _appendNewLines()
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Toolbar
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            color: Qt.darker(surface, 1.2)

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10; anchors.rightMargin: 8
                spacing: 8

                SectionLabel { text: "Console"; accentColor: accent }

                Item { Layout.fillWidth: true }

                // Test DBs button
                Rectangle {
                    implicitWidth: 64; implicitHeight: 22; radius: 6
                    color: testDbMouse.containsMouse
                           ? Qt.rgba(accent.r, accent.g, accent.b, 0.18)
                           : "transparent"
                    border.width: 1
                    border.color: Qt.rgba(border_.r, border_.g, border_.b, 0.5)
                    Behavior on color { ColorAnimation { duration: 100 } }
                    Text {
                        anchors.centerIn: parent
                        text: "Test DBs"
                        color: testDbMouse.containsMouse ? accent : dim
                        font.pixelSize: 10
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    MouseArea {
                        id: testDbMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.testDatabases()
                    }
                }

                // Copy All button
                Rectangle {
                    implicitWidth: 64; implicitHeight: 22; radius: 6
                    color: copyMouse.containsMouse
                           ? Qt.rgba(accent.r, accent.g, accent.b, 0.18)
                           : "transparent"
                    border.width: 1
                    border.color: Qt.rgba(border_.r, border_.g, border_.b, 0.5)
                    Behavior on color { ColorAnimation { duration: 100 } }
                    Text {
                        anchors.centerIn: parent
                        text: copyMouse.pressed ? "Copied!" : "Copy All"
                        color: copyMouse.containsMouse ? accent : dim
                        font.pixelSize: 10
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    MouseArea {
                        id: copyMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            clipHelper.text = backend.consoleLog
                            clipHelper.selectAll()
                            clipHelper.copy()
                        }
                    }
                }

                // Chip-style Clear button
                Rectangle {
                    implicitWidth: 54; implicitHeight: 22; radius: 6
                    color: "transparent"
                    border.width: 1
                    border.color: Qt.rgba(border_.r, border_.g, border_.b, 0.5)
                    Text {
                        anchors.centerIn: parent
                        text: "Clear"
                        color: dim; font.pixelSize: 10
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.clearConsole()
                    }
                }

                // Hidden TextEdit used as clipboard helper
                TextEdit {
                    id: clipHelper
                    visible: false
                    width: 0; height: 0
                }
            }
        }

        // Console output — color-coded ListView
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#0d1117"

            ListView {
                id: consoleListView
                anchors.fill: parent
                anchors.margins: 6
                model: consoleModel
                clip: true
                spacing: 1

                onCountChanged: {
                    Qt.callLater(function() { consoleListView.positionViewAtEnd() })
                }

                delegate: Item {
                    width: consoleListView.width
                    height: 18

                    required property var model
                    property string tag: root.lineTag(model.lineText)

                    Row {
                        anchors.fill: parent
                        spacing: 5

                        // Tag chip
                        Rectangle {
                            width: tag.length > 0 ? 38 : 0
                            height: 14
                            radius: 3
                            anchors.verticalCenter: parent.verticalCenter
                            color: {
                                if (tag === "WARN")  return "#3a3000"
                                if (tag === "ERROR") return "#3c1010"
                                if (tag === "INFO")  return Qt.rgba(accent.r * 0.3, accent.g * 0.3, accent.b * 0.3, 1)
                                if (tag === "AI")    return "#0f2a0f"
                                return "transparent"
                            }
                            visible: tag.length > 0

                            Text {
                                anchors.centerIn: parent
                                text: tag
                                font.pixelSize: 8; font.bold: true
                                color: root.lineColor(tag)
                            }
                        }

                        Text {
                            text: root.lineBody(model.lineText, tag)
                            anchors.verticalCenter: parent.verticalCenter
                            color: root.lineColor(tag)
                            font.family: "Consolas"
                            font.pixelSize: 10
                        }
                    }
                }
            }

            // Subtle scanline overlay
            Canvas {
                anchors.fill: parent
                opacity: 1.0

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)
                    ctx.fillStyle = Qt.rgba(0, 0, 0, 0.025)
                    for (var y = 0; y < height; y += 4) {
                        ctx.fillRect(0, y, width, 2)
                    }
                }
            }
        }
    }
}
