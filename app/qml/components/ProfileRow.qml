import QtQuick
import QtQuick.Layouts
import theme 1.0
import "."

GlassCard {
    id: root
    property string name: "Profile"
    property string ident: "#0000"
    property string browser: "Camoufox"
    property string proxy: "None"
    property string lastActive: "idle"
    property string status: "Stopped"
    property string tags: "#profile"
    property bool running: false
    signal startClicked()
    signal stopClicked()
    signal settingsClicked()
    signal deleteClicked()
    signal contextRequested(real x, real y)
    height: 78
    padding: 18

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.RightButton
        propagateComposedEvents: true
        onClicked: function(mouse) {
            if (mouse.button === Qt.RightButton)
                root.contextRequested(mouse.x, mouse.y)
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: Math.max(8, Math.min(18, root.width / 80))

        Rectangle {
            Layout.preferredWidth: 42; Layout.preferredHeight: 42; radius: 14
            Layout.alignment: Qt.AlignVCenter
            color: running ? "#0c3345" : "#25233a"
            LineIcon { anchors.centerIn: parent; name: "globe"; color: running ? Theme.success : Theme.dim; size: 22 }
        }

        Column {
            Layout.preferredWidth: 260
            Layout.minimumWidth: 100
            Layout.maximumWidth: 360
            Layout.alignment: Qt.AlignVCenter
            spacing: 5
            Row { width: parent.width; spacing: 8; Text { text: root.name; color: Theme.text; font.pixelSize: 15; font.bold: true; elide: Text.ElideRight; width: Math.max(30, parent.width - identText.width - 8) } Text { id: identText; text: root.ident; color: Theme.dim; font.pixelSize: 12 } }
            Text { text: root.tags; color: Theme.primaryLight; font.pixelSize: 12; elide: Text.ElideRight; width: parent.width }
        }

        InfoColumn { title: "Browser"; value: root.browser; Layout.minimumWidth: 72; Layout.preferredWidth: 100 }
        InfoColumn { title: "Proxy"; value: root.proxy; Layout.fillWidth: true; Layout.minimumWidth: 90; Layout.preferredWidth: 180 }
        InfoColumn { title: "Last Active"; value: root.lastActive; Layout.minimumWidth: 68; Layout.preferredWidth: 90 }

        Row {
            Layout.minimumWidth: 24
            Layout.preferredWidth: 96
            Layout.alignment: Qt.AlignVCenter
            spacing: 8
            Rectangle { width: 7; height: 7; radius: 4; color: running ? Theme.success : Theme.dim; anchors.verticalCenter: parent.verticalCenter }
            Text { text: root.status; color: Theme.muted; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight; width: parent.width - 15 }
        }

        Row {
            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
            Layout.minimumWidth: 124
            spacing: 8
            PrimaryButton { width: 36; icon: running ? "stop" : "play"; text: ""; secondary: true; onClicked: running ? root.stopClicked() : root.startClicked() }
            PrimaryButton { width: 36; icon: "settings"; text: ""; secondary: true; onClicked: root.settingsClicked() }
            PrimaryButton { width: 36; icon: "trash"; text: ""; danger: true; onClicked: root.deleteClicked() }
        }
    }
}
