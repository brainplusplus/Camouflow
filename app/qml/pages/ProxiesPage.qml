import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import theme 1.0
import "../components"

Flickable {
    id: root
    contentWidth: width
    contentHeight: content.height + 48
    clip: true
    property var bridge: typeof proxiesBridge !== "undefined" ? proxiesBridge : null

    Column {
        id: content
        width: parent.width - 56
        x: 28; y: 24; spacing: 22

        RowLayout {
            width: parent.width
            PageHeader { Layout.fillWidth: true; title: "Proxies"; subtitle: "Proxy pools, assignments and health checks" }
            PrimaryButton { width: 120; text: "Import List"; icon: "save"; secondary: true; onClicked: addPanel.visible = true }
            PrimaryButton { width: 120; text: "Add Proxy"; icon: "plus"; onClicked: addPanel.visible = !addPanel.visible }
        }

        GridLayout { width: parent.width; columns: 4; columnSpacing: 14
            StatCard { Layout.fillWidth: true; height: 82; label: "Active"; value: root.bridge ? root.bridge.active : 0; icon: "globe"; accent: Theme.success }
            StatCard { Layout.fillWidth: true; height: 82; label: "Checking"; value: root.bridge ? root.bridge.checking : 0; icon: "zap"; accent: Theme.warning }
            StatCard { Layout.fillWidth: true; height: 82; label: "Failed"; value: root.bridge ? root.bridge.failed : 0; icon: "trash"; accent: Theme.danger }
            StatCard { Layout.fillWidth: true; height: 82; label: "Locations"; value: root.bridge ? root.bridge.locations : 0; icon: "network"; accent: Theme.primary }
        }

        GlassCard { id: addPanel; width: parent.width; height: visible ? 150 : 0; visible: false; padding: 18
            Row { anchors.fill: parent; spacing: 12
                Column { width: parent.width - 150; spacing: 8
                    Text { text: "Proxy list"; color: Theme.text; font.pixelSize: 12; font.bold: true }
                    Rectangle { width: parent.width; height: 92; radius: 11; color: Theme.subtle; border.color: Theme.border
                        TextArea {
                            id: proxyInput
                            anchors.fill: parent
                            anchors.margins: 10
                            color: Theme.text
                            placeholderText: "socks5://host:port:user:password\nhttp://user:pass@host:port"
                            placeholderTextColor: Theme.dim
                            background: Item {}
                            font.pixelSize: 13
                        }
                    }
                }
                PrimaryButton { width: 120; text: "Add"; icon: "plus"; anchors.bottom: parent.bottom; onClicked: { if (root.bridge) root.bridge.addProxies(proxyInput.text); proxyInput.text = "" } }
            }
        }

        RowLayout {
            width: parent.width
            spacing: 18

            GlassCard {
                Layout.preferredWidth: 300
                Layout.preferredHeight: 560
                padding: 18
                Text { id: poolsTitle; text: "Proxy groups"; color: Theme.text; font.pixelSize: 16; font.bold: true }
                Row { id: poolActions; anchors.left: parent.left; anchors.right: parent.right; anchors.top: poolsTitle.bottom; anchors.topMargin: 14; spacing: 8
                    PrimaryButton { width: (parent.width - 16) / 3; text: "New"; icon: "plus"; onClicked: { poolNameInput.text = ""; poolDialog.mode = "new"; poolDialog.open() } }
                    PrimaryButton { width: (parent.width - 16) / 3; text: "Rename"; secondary: true; onClicked: { poolNameInput.text = root.bridge ? root.bridge.selectedPool : ""; poolDialog.mode = "rename"; poolDialog.open() } }
                    PrimaryButton { width: (parent.width - 16) / 3; text: "Delete"; danger: true; onClicked: if (root.bridge) root.bridge.deleteSelectedPool() }
                }
                ListView {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: poolActions.bottom
                    anchors.topMargin: 14
                    anchors.bottom: parent.bottom
                    model: root.bridge ? root.bridge.poolsModel : null
                    spacing: 8
                    clip: true
                    delegate: Rectangle {
                        width: ListView.view.width
                        height: 54
                        radius: 12
                        color: model.selected ? "#35285a" : Theme.subtle
                        border.color: model.selected ? Theme.primary : Theme.border
                        Text { anchors.left: parent.left; anchors.leftMargin: 12; anchors.top: parent.top; anchors.topMargin: 9; text: model.name; color: Theme.text; font.pixelSize: 13; font.bold: true; elide: Text.ElideRight; width: parent.width - 72 }
                        Text { anchors.left: parent.left; anchors.leftMargin: 12; anchors.bottom: parent.bottom; anchors.bottomMargin: 9; text: model.total + " proxies ? " + model.used + " used"; color: Theme.dim; font.pixelSize: 11 }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: if (root.bridge) root.bridge.selectPool(model.name) }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 560
                GlassCard { Layout.fillWidth: true; Layout.preferredHeight: 64; padding: 14
                    Row { anchors.fill: parent; spacing: 12
                        Text { text: root.bridge && root.bridge.selectedPool ? "Group: " + root.bridge.selectedPool : "All proxy groups"; color: Theme.text; font.pixelSize: 16; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
                        Item { width: Math.max(0, parent.width - 620); height: 1 }
                        PrimaryButton { width: 130; text: "Check Group"; icon: "settings"; secondary: true; onClicked: if (root.bridge) root.bridge.checkAll() }
                        PrimaryButton { width: 120; text: "Release"; secondary: true; onClicked: if (root.bridge) root.bridge.releaseSelected() }
                        PrimaryButton { width: 120; text: "Remove"; danger: true; onClicked: if (root.bridge) root.bridge.removeSelected() }
                        PrimaryButton { width: 90; text: "Clear"; secondary: true; onClicked: if (root.bridge) root.bridge.clearSelection() }
                    }
                }
                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: root.bridge ? root.bridge.model : null
                    spacing: 12
                    clip: true
                    delegate: ProxyRow {
                        width: ListView.view.width
                        pool: model.pool
                        proxyIndex: model.index
                        name: model.name
                        location: model.location
                        address: model.address
                        type: model.type
                        latency: model.latency
                        status: model.status
                        accent: model.accent
                        selected: model.selected
                        onSelectionToggled: function(pool, index, selected) {
                            if (root.bridge) root.bridge.setProxySelected(pool, index, selected)
                        }
                        onSettingsClicked: function(pool, index) {
                            var payload = root.bridge ? root.bridge.getProxy(pool, index) : {}
                            proxyEditPool.text = payload.pool || pool
                            proxyEditIndex.text = String(payload.index !== undefined ? payload.index : index)
                            proxyEditName.text = payload.name || ""
                            proxyEditValue.text = payload.value || ""
                            proxyEditDialog.open()
                        }
                        onCheckClicked: function(pool, index) {
                            if (root.bridge) root.bridge.checkProxy(pool, index)
                        }
                        onDeleteClicked: function(pool, index) {
                            if (root.bridge) root.bridge.deleteProxy(pool, index)
                        }
                    }
                }
            }
        }
    }

    Dialog {
        id: poolDialog
        property string mode: "new"
        modal: true
        width: 420; height: 210
        anchors.centerIn: Overlay.overlay
        padding: 0
        background: Rectangle { color: Theme.elevated; radius: 18; border.color: Theme.border }
        contentItem: Column { anchors.fill: parent; anchors.margins: 22; spacing: 16
            Text { text: poolDialog.mode === "rename" ? "Rename proxy group" : "New proxy group"; color: Theme.text; font.pixelSize: 20; font.bold: true }
            FormField { id: poolNameInput; width: parent.width; label: "Group name"; placeholder: "US residential" }
            Row { spacing: 10
                PrimaryButton { width: 120; text: "Save"; icon: "save"; onClicked: { if (root.bridge) { if (poolDialog.mode === "rename") root.bridge.renameSelectedPool(poolNameInput.text); else root.bridge.createPool(poolNameInput.text) } poolDialog.close() } }
                PrimaryButton { width: 120; text: "Cancel"; secondary: true; onClicked: poolDialog.close() }
            }
        }
    }

    Dialog {
        id: proxyEditDialog
        modal: true
        width: 560
        height: 330
        anchors.centerIn: Overlay.overlay
        padding: 0
        background: Rectangle { color: Theme.elevated; radius: 18; border.color: Theme.border }
        contentItem: Column {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 14
            Text { text: "Proxy Settings"; color: Theme.text; font.pixelSize: 20; font.bold: true }
            FormField { id: proxyEditPool; visible: false; width: parent.width; label: "Pool" }
            FormField { id: proxyEditIndex; visible: false; width: parent.width; label: "Index" }
            FormField { id: proxyEditName; width: parent.width; label: "Name"; placeholder: "Optional display name" }
            FormField { id: proxyEditValue; width: parent.width; label: "Proxy"; placeholder: "socks5://host:port:user:password" }
            Row {
                spacing: 10
                PrimaryButton {
                    width: 130
                    text: "Save"
                    icon: "save"
                    onClicked: {
                        if (root.bridge) root.bridge.saveProxy(proxyEditPool.text, parseInt(proxyEditIndex.text), proxyEditName.text, proxyEditValue.text)
                        proxyEditDialog.close()
                    }
                }
                PrimaryButton { width: 120; text: "Cancel"; secondary: true; onClicked: proxyEditDialog.close() }
            }
        }
    }
}
