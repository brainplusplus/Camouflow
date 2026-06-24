import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import theme 1.0
import "../components"

Flickable {
    id: root
    contentWidth: width
    contentHeight: content.height + 48
    clip: true
    property string editingProfile: ""
    property string contextProfile: ""
    property var selectedTags: []

    // gpuPresetModel indices: 0 = Inherit, 1 = Custom, 2+ = concrete presets
    ListModel {
        id: gpuPresetModel
        ListElement { name: "Inherit" }
        ListElement { name: "Custom" }
    }
    // screenResModel indices: 0 = Inherit, 1 = Custom, 2+ = concrete presets
    ListModel {
        id: screenResModel
        ListElement { name: "Inherit"; width: 0; height: 0 }
        ListElement { name: "Custom"; width: 0; height: 0 }
    }
    ListModel { id: tagSelectorModel }
    ListModel { id: proxyPoolModel }

    function updateProxyVisibility() {
        var mode = proxyModeCombo.currentText.toLowerCase()
        var enabled = proxyEnable.checked
        proxyModeRow.visible = enabled
        proxyPoolRow.visible = enabled && (mode === "random" || mode === "fixed")
        proxyFixedProxyRow.visible = enabled && mode === "fixed"
        proxyManualRow.visible = enabled && (mode === "manual" || mode === "fixed")
    }

    function loadFixedProxyList() {
        proxyFixedProxyCombo.model = []
        var poolName = proxyPoolCombo.currentText
        if (!poolName) return
        try {
            var items = JSON.parse(profilesBridge.getProxiesForPool(poolName))
            var labels = []
            for (var i = 0; i < items.length; i++) {
                labels.push(items[i].label || items[i].value)
            }
            proxyFixedProxyCombo.model = labels.length ? labels : ["(no proxies)"]
        } catch(e) {
            proxyFixedProxyCombo.model = ["(error)"]
        }
    }

    function onFixedProxySelected() {
        var poolName = proxyPoolCombo.currentText
        if (!poolName) return
        var proxyLabel = proxyFixedProxyCombo.currentText
        if (!proxyLabel || proxyLabel === "(no proxies)" || proxyLabel === "(error)") return
        try {
            var items = JSON.parse(profilesBridge.getProxiesForPool(poolName))
            for (var i = 0; i < items.length; i++) {
                if ((items[i].label || items[i].value) === proxyLabel) {
                    var details = profilesBridge.getProxyFromPool(poolName, String(items[i].index))
                    editorProxyHost.text = details.proxy_host || ""
                    editorProxyPort.text = details.proxy_port ? String(details.proxy_port) : ""
                    editorProxyUser.text = details.proxy_user || ""
                    editorProxyPassword.text = details.proxy_password || ""
                    return
                }
            }
        } catch(e) {}
    }

    function updateEngineSpecific() {
        var isCloak = editorEngine.currentText === "CloakBrowser"
        launchArgsSection.visible = isCloak
        fingerprintSeedSection.visible = isCloak
    }

    function refreshTagList() {
        var all = JSON.parse(profilesBridge.getAllTags())
        tagSelectorModel.clear()
        for (var i = 0; i < all.length; i++) {
            tagSelectorModel.append({ "name": all[i], "checked": selectedTags.indexOf(all[i]) >= 0 })
        }
    }

    function toggleTag(tagName) {
        var idx = selectedTags.indexOf(tagName)
        if (idx >= 0)
            selectedTags.splice(idx, 1)
        else
            selectedTags.push(tagName)
        refreshTagList()
    }

    function collectProfileData() {
        var mode = proxyEnable.checked ? proxyModeCombo.currentText.toLowerCase() : "none"
        var data = {
            "name": editorName.text,
            "engine": editorEngine.currentText === "CloakBrowser" ? "cloakbrowser" : "camoufox",
            "tags": selectedTags,
            "notes": editorNotes.text,
            "proxy_mode": mode,
            "proxy_pool": (mode === "random" || mode === "fixed") ? proxyPoolCombo.currentText : "",
            "proxy_host": "",
            "proxy_port": "",
            "proxy_user": "",
            "proxy_password": "",
            "proxy_scheme": "socks5",
        }
        if (mode === "manual" || mode === "fixed") {
            data.proxy_host = editorProxyHost.text
            data.proxy_port = editorProxyPort.text
            data.proxy_user = editorProxyUser.text
            data.proxy_password = editorProxyPassword.text
        }

        var sw = parseInt(editorScreenWidth.text || "0")
        var sh = parseInt(editorScreenHeight.text || "0")
        var overrides = {
            "locale": editorLocale.text,
            "timezone": editorTimezone.text,
            "user_agent": editorUserAgent.text,
            "gpu_vendor": editorGpuVendor.text,
            "gpu_renderer": editorGpuRenderer.text,
            "hardware_concurrency": parseInt(editorCpu.text || "0"),
            "platform": platformCombo.currentText.toLowerCase(),
            "humanize": humanizeCheckbox.checked,
            "human_preset": humanPresetCombo.currentText,
            "geoip": geoipCheckbox.checked,
            "block_images": !loadImagesCheckbox.checked,
            "screen_width": sw,
            "screen_height": sh,
            "launch_args": launchArgsField.text.trim() ? launchArgsField.text.split("\n").map(function(s){return s.trim()}).filter(function(s){return s.length>0}) : [],
            "fingerprint_seed": parseInt(editorFpSeed.text || "0"),
            "color_scheme": "",
        }
        data.overrides = overrides
        return data
    }

    function generateSeed() {
        editorFpSeed.text = String(Math.floor(Math.random() * 999999) + 1)
    }

    function openProfileModal(profileName) {
        root.editingProfile = profileName
        var data = profilesBridge.getProfileData(profileName)
        editorName.text = data.name || profileName
        editorEngine.currentIndex = data.engine === "cloakbrowser" ? 1 : 0

        // Tags
        selectedTags = (data.tags instanceof Array) ? data.tags.slice() : []
        refreshTagList()

        // Notes
        editorNotes.text = data.notes || ""

        // Proxy
        var pm = data.proxy_mode || "none"
        proxyEnable.checked = pm !== "none"
        // Combo no longer has "None"; Random=0, Fixed=1, Manual=2
        var pmIdx = ["random","fixed","manual"].indexOf(pm)
        proxyModeCombo.currentIndex = pmIdx >= 0 ? pmIdx : 0
        proxyPoolCombo.currentIndex = Math.max(0, proxyPoolCombo.find(data.proxy_pool || ""))
        if (pm === "fixed") {
            root.loadFixedProxyList()
        } else {
            proxyFixedProxyCombo.model = []
        }
        editorProxyHost.text = data.proxy_host || ""
        editorProxyPort.text = data.proxy_port || ""
        editorProxyUser.text = data.proxy_user || ""
        editorProxyPassword.text = data.proxy_password || ""
        updateProxyVisibility()

        // Overrides
        var ov = data.overrides || {}
        editorLocale.text = ov.locale || ""
        editorTimezone.text = ov.timezone || ""
        editorUserAgent.text = ov.user_agent || ""
        editorNotes.text = data.notes || ""
        geoipCheckbox.checked = !!ov.geoip
        humanizeCheckbox.checked = !!ov.humanize
        loadImagesCheckbox.checked = !ov.block_images
        humanPresetCombo.currentIndex = ["default","careful"].indexOf(ov.human_preset || "default")
        platformCombo.currentIndex = ["","windows","linux","macos"].indexOf(ov.platform || "")
        // GPU Preset: 0=Inherit, 1=Custom, 2+=concrete presets
        var gpuVendor = ov.gpu_vendor || ""
        var gpuRenderer = ov.gpu_renderer || ""
        editorGpuVendor.text = gpuVendor
        editorGpuRenderer.text = gpuRenderer
        var gpuIdx = 0 // default Inherit
        if (!gpuVendor && !gpuRenderer) {
            gpuIdx = 0 // Inherit
        } else {
            // Try to match a concrete preset
            gpuIdx = 1 // Custom if no preset matches
            try {
                var gpuPresets = JSON.parse(profilesBridge.getGpuPresets())
                for (var gp = 0; gp < gpuPresets.length; gp++) {
                    if (gpuPresets[gp].vendor === gpuVendor && gpuPresets[gp].renderer === gpuRenderer) {
                        gpuIdx = gp + 2 // presets start at index 2
                        break
                    }
                }
            } catch(e) {}
        }
        gpuPresetCombo.currentIndex = gpuIdx
        editorCpu.text = ov.hardware_concurrency ? String(ov.hardware_concurrency) : ""
        // Screen Resolution: 0=Inherit, 1=Custom, 2+=concrete presets
        var sw = ov.screen_width || 0
        var sh = ov.screen_height || 0
        var resIdx = 0 // default Inherit
        if (!sw && !sh) {
            resIdx = 0 // Inherit
            editorScreenWidth.text = ""
            editorScreenHeight.text = ""
        } else {
            resIdx = 1 // Custom if no preset matches
            for (var ri = 2; ri < screenResModel.count; ri++) {
                var rItem = screenResModel.get(ri)
                if (rItem.width === sw && rItem.height === sh) {
                    resIdx = ri
                    break
                }
            }
            editorScreenWidth.text = String(sw)
            editorScreenHeight.text = String(sh)
        }
        screenResCombo.currentIndex = resIdx
        editorFpSeed.text = ov.fingerprint_seed ? String(ov.fingerprint_seed) : ""
        launchArgsField.text = (ov.launch_args instanceof Array) ? ov.launch_args.join("\n") : ""

        updateEngineSpecific()
        profileDialog.open()
    }
    function openVariablesModal(profileName) {
        editingProfile = profileName || editingProfile
        profileVarsJson.text = profilesBridge.getProfileVariables(editingProfile)
        profileVarsDialog.open()
    }
    function openCookiesModal(profileName) {
        editingProfile = profileName || editingProfile
        profileCookiesJson.text = profilesBridge.getProfileCookiesJson(editingProfile)
        profileCookiesDialog.open()
    }
    function openTagsModal() {
        settingsBridge.refresh()
        tagName.text = ""
        tagsDialog.open()
    }

    Component.onCompleted: {
        // Populate GPU presets model (0=Inherit, 1=Custom already in model)
        try {
            var presets = JSON.parse(profilesBridge.getGpuPresets())
            for (var i = 0; i < presets.length; i++)
                gpuPresetModel.append({ name: presets[i].name })
        } catch(e) {}
        // Populate screen resolution presets (0=Inherit, 1=Custom already in model)
        try {
            var resolutions = JSON.parse(profilesBridge.getScreenResolutionPresets())
            for (var j = 0; j < resolutions.length; j++)
                screenResModel.append({ name: resolutions[j].name, width: resolutions[j].width, height: resolutions[j].height })
        } catch(e) {}
    }

    Column {
        id: content
        width: parent.width - 56
        x: 28
        y: 24
        spacing: 22
        RowLayout {
            width: parent.width
            PageHeader { Layout.fillWidth: true; title: "Profiles"; subtitle: "Manage your browser profiles and sessions" }
            PrimaryButton { Layout.preferredWidth: 116; height: 42; text: "Import"; icon: "save"; secondary: true; onClicked: importDialog.open() }
            PrimaryButton { Layout.preferredWidth: 116; height: 42; text: "Tags"; icon: "settings"; secondary: true; onClicked: root.openTagsModal() }
            PrimaryButton { Layout.preferredWidth: 116; height: 42; text: "New Profile"; icon: "plus"; onClicked: profilesBridge.createProfile() }
        }
        SearchBox { id: search; width: parent.width; placeholder: "Search profiles or tags..." }
        ListView {
            width: parent.width
            height: 38
            orientation: ListView.Horizontal
            spacing: 8
            model: profilesBridge ? profilesBridge.stagesModel : null
            clip: true
            delegate: Rectangle {
                width: tagText.width + 34
                height: 34
                radius: 11
                color: model.selected ? Theme.primary : Theme.subtle
                border.color: model.selected ? Theme.primaryLight : Theme.border
                Text {
                    id: tagText
                    anchors.centerIn: parent
                    text: model.name + "  " + model.count
                    color: model.selected ? "white" : Theme.muted
                    font.pixelSize: 12
                    font.bold: true
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: profilesBridge.setStageFilter(model.name) }
            }
        }
        ListView {
            width: parent.width
            height: Math.max(520, count * 92)
            model: profilesBridge ? profilesBridge.model : null
            spacing: 14
            interactive: false
            delegate: ProfileRow {
                width: ListView.view.width
                name: model.name
                ident: model.id
                browser: model.browser
                proxy: model.proxy
                lastActive: model.lastActive
                status: model.status
                tags: model.tags
                running: model.running
                visible: search.text.length === 0 || (model.name + model.tags + model.proxy).toLowerCase().indexOf(search.text.toLowerCase()) >= 0
                height: visible ? 78 : 0
                onStartClicked: profilesBridge.startProfile(model.name)
                onStopClicked: profilesBridge.stopProfile(model.name)
                onSettingsClicked: root.openProfileModal(model.name)
                onDeleteClicked: profilesBridge.deleteProfile(model.name)
                onContextRequested: function(x, y) {
                    root.contextProfile = model.name
                    profileMenu.popup(x + 28, y + 150)
                }
            }
        }
        GlassCard {
            width: parent.width
            height: 118
            padding: 18
            RowLayout {
                anchors.fill: parent
                spacing: 12
                Column {
                    Layout.preferredWidth: 210
                    spacing: 6
                    Text { text: "Run scenario for tag"; color: Theme.text; font.pixelSize: 16; font.bold: true }
                    Text { text: "Batch run selected scenario by profile tag"; color: Theme.muted; font.pixelSize: 12 }
                }
                Rectangle {
                    Layout.preferredWidth: 180
                    height: 42
                    radius: 11
                    color: Theme.subtle
                    border.color: Theme.border
                    ComboBox {
                        id: runTagSelect
                        anchors.fill: parent
                        anchors.margins: 6
                        model: profilesBridge ? profilesBridge.stagesModel : null
                        textRole: "name"
                        background: Item {}
                        contentItem: Text { text: runTagSelect.displayText || "Tag"; color: Theme.text; verticalAlignment: Text.AlignVCenter; font.pixelSize: 13; elide: Text.ElideRight }
                    }
                }
                Rectangle {
                    Layout.preferredWidth: 240
                    height: 42
                    radius: 11
                    color: Theme.subtle
                    border.color: Theme.border
                    ComboBox {
                        id: runScenarioSelect
                        anchors.fill: parent
                        anchors.margins: 6
                        model: scenariosBridge ? scenariosBridge.model : null
                        textRole: "name"
                        background: Item {}
                        contentItem: Text { text: runScenarioSelect.displayText || "Scenario"; color: Theme.text; verticalAlignment: Text.AlignVCenter; font.pixelSize: 13; elide: Text.ElideRight }
                    }
                }
                FormField { id: runMax; Layout.preferredWidth: 90; label: "Max"; text: "10" }
                PrimaryButton {
                    Layout.preferredWidth: 130
                    text: "Run for tag"
                    icon: "play"
                    onClicked: scenariosBridge.runForTag(runTagSelect.currentText, runScenarioSelect.currentText, parseInt(runMax.text || "1"))
                }
                PrimaryButton { Layout.preferredWidth: 120; text: "Variables"; icon: "settings"; secondary: true; onClicked: variablesDialog.open() }
            }
        }
    }

    Dialog {
        id: importDialog
        modal: true
        width: Math.min(900, root.width - 80)
        height: Math.min(680, root.height - 80)
        anchors.centerIn: Overlay.overlay
        padding: 0
        background: Rectangle { color: Theme.elevated; radius: 22; border.color: Theme.border }
        contentItem: Column {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 14
            Text { text: "Import Profiles"; color: Theme.text; font.pixelSize: 24; font.bold: true }
            FormField { id: importTemplate; width: parent.width; label: "Account parse template"; text: "{email};{password};{secret_key};{extra};{twofa_url}" }
            Row {
                width: parent.width
                spacing: 12
                FormField { id: importTag; width: (parent.width - 12) / 2; label: "Default tag" }
                Rectangle {
                    width: (parent.width - 12) / 2
                    height: 62
                    color: "transparent"
                    Text { text: "Proxy pool"; color: Theme.text; font.pixelSize: 12; font.bold: true }
                    Rectangle {
                        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                        height: 40; radius: 11; color: Theme.subtle; border.color: Theme.border
                        ComboBox {
                            id: importProxyPool
                            anchors.fill: parent
                            anchors.margins: 6
                            model: proxiesBridge ? proxiesBridge.poolsModel : null
                            textRole: "name"
                            background: Item {}
                            contentItem: Text { text: importProxyPool.displayText || "Default"; color: Theme.text; verticalAlignment: Text.AlignVCenter; font.pixelSize: 13 }
                        }
                    }
                }
            }
            Text { text: "Profiles, one per line"; color: Theme.text; font.pixelSize: 12; font.bold: true }
            Rectangle {
                width: parent.width
                height: parent.height - 230
                radius: 14
                color: Theme.subtle
                border.color: Theme.border
                TextArea {
                    id: importLines
                    anchors.fill: parent
                    anchors.margins: 12
                    color: Theme.text
                    placeholderText: "user@example.com;pass123;SECRET;note;https://2fa.example.com/"
                    placeholderTextColor: Theme.dim
                    background: Item {}
                    font.pixelSize: 13
                }
            }
            Row {
                spacing: 10
                PrimaryButton {
                    width: 120
                    text: "Import"
                    icon: "save"
                    onClicked: {
                        profilesBridge.importProfiles(importLines.text, importTemplate.text, importTag.text, importProxyPool.currentText === "All pools" ? "" : importProxyPool.currentText)
                        importDialog.close()
                    }
                }
                PrimaryButton { width: 100; text: "Cancel"; secondary: true; onClicked: importDialog.close() }
            }
        }
    }

    Dialog {
        id: tagsDialog
        modal: true
        width: Math.min(480, root.width - 80)
        height: 520
        anchors.centerIn: Overlay.overlay
        padding: 0
        background: Rectangle { color: Theme.elevated; radius: 22; border.color: Theme.border }
        contentItem: Column {
            spacing: 14
            padding: 22
            RowLayout {
                width: parent.width - 44
                Text { text: "Profile Tags"; color: Theme.text; font.pixelSize: 22; font.bold: true; Layout.fillWidth: true }
                PrimaryButton { Layout.preferredWidth: 40; text: ""; icon: "plus"; onClicked: tagCreateDialog.open() }
            }
            Text { width: parent.width - 44; text: "Create tags here, then assign them in profile settings."; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.WordWrap }
            ListView {
                width: parent.width - 44
                height: 360
                model: settingsBridge ? settingsBridge.stagesModel : null
                spacing: 8
                clip: true
                delegate: Rectangle {
                    width: ListView.view.width
                    height: 42
                    radius: 11
                    color: Theme.subtle
                    border.color: Theme.border
                    Text { anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: model.name; color: Theme.text; font.pixelSize: 13; font.bold: true }
                    PrimaryButton { anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter; width: 34; height: 28; text: ""; icon: "trash"; danger: true; onClicked: { settingsBridge.deleteStage(model.name); profilesBridge.refresh() } }
                }
            }
        }
    }

    Dialog {
        id: tagCreateDialog
        modal: true
        width: Math.min(420, root.width - 100)
        height: 210
        anchors.centerIn: Overlay.overlay
        padding: 0
        background: Rectangle { color: Theme.elevated; radius: 20; border.color: Theme.border }
        contentItem: Column {
            spacing: 14
            padding: 22
            Text { text: "New Tag"; color: Theme.text; font.pixelSize: 20; font.bold: true }
            FormField { id: tagName; width: parent.width - 44; label: "Tag name" }
            Row {
                spacing: 10
                PrimaryButton { width: 110; text: "Create"; icon: "plus"; onClicked: { settingsBridge.addStage(tagName.text); profilesBridge.refresh(); tagCreateDialog.close() } }
                PrimaryButton { width: 100; text: "Cancel"; secondary: true; onClicked: tagCreateDialog.close() }
            }
        }
    }

    Dialog {
        id: profileDialog
        modal: true
        width: Math.min(880, root.width - 80)
        height: Math.min(860, root.height - 60)
        anchors.centerIn: Overlay.overlay
        padding: 0
        background: Rectangle { color: Theme.elevated; radius: 22; border.color: Theme.border }
        contentItem: Flickable {
            contentWidth: width
            contentHeight: modalContent.height + 44
            clip: true
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            Column {
                id: modalContent
                width: parent.width - 44
                x: 22
                y: 22
                spacing: 20

                // --- Header ---
                RowLayout {
                    width: parent.width
                    Text { text: "Profile Settings"; color: Theme.text; font.pixelSize: 24; font.bold: true; Layout.fillWidth: true }
                    Row {
                        spacing: 8
                        Text { text: "Engine:"; color: Theme.muted; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                        DarkComboBox {
                            id: editorEngine
                            width: 160; height: 34
                            model: ["Camoufox", "CloakBrowser"]
                            onActivated: updateEngineSpecific()
                        }
                    }
                }

                FormField { id: editorName; width: parent.width; label: "Profile Name" }

                // --- Tags section ---
                Column {
                    width: parent.width
                    spacing: 10
                    Text { text: "Tags"; color: Theme.text; font.pixelSize: 16; font.bold: true }
                    Flow {
                        width: parent.width
                        spacing: 6
                        Repeater {
                            model: tagSelectorModel
                            delegate: Rectangle {
                                width: tagChipText.width + 28; height: 30; radius: 9
                                color: model.checked ? Theme.primary : Theme.subtle
                                border.color: model.checked ? Theme.primaryLight : Theme.border
                                Text { id: tagChipText; anchors.centerIn: parent; text: model.name; color: model.checked ? "white" : Theme.muted; font.pixelSize: 12; font.bold: true }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.toggleTag(model.name) }
                            }
                        }
                    }
                }

                // --- Proxy section ---
                Column {
                    width: parent.width
                    spacing: 12
                    Rectangle { width: parent.width; height: 1; color: Theme.border }
                    Row {
                        width: parent.width
                        spacing: 10
                        Text { text: "Proxy"; color: Theme.text; font.pixelSize: 16; font.bold: true; Layout.fillWidth: true; anchors.verticalCenter: parent.verticalCenter }
                        DarkCheckBox { id: proxyEnable; text: "Enable"; checked: false; onCheckedChanged: root.updateProxyVisibility() }
                    }
                    Row {
                        id: proxyModeRow
                        width: parent.width
                        visible: false
                        spacing: 10
                        Text { text: "Mode"; color: Theme.muted; font.pixelSize: 13; width: 70; anchors.verticalCenter: parent.verticalCenter }
                        DarkComboBox {
                            id: proxyModeCombo
                            width: 200; height: 36
                            model: ["Random", "Fixed", "Manual"]
                            onActivated: root.updateProxyVisibility()
                        }
                    }
                    Row {
                        id: proxyPoolRow
                        width: parent.width
                        visible: false
                        spacing: 10
                        Text { text: "Pool"; color: Theme.muted; font.pixelSize: 13; width: 70; anchors.verticalCenter: parent.verticalCenter }
                        DarkComboBox {
                            id: proxyPoolCombo
                            width: 240; height: 36
                            model: profilesBridge ? profilesBridge.proxyPoolsModel : null
                            textRole: "name"
                            onActivated: {
                                if (proxyModeCombo.currentText.toLowerCase() === "fixed")
                                    root.loadFixedProxyList()
                            }
                        }
                    }
                    Row {
                        id: proxyFixedProxyRow
                        width: parent.width
                        visible: false
                        spacing: 10
                        Text { text: "Proxy"; color: Theme.muted; font.pixelSize: 13; width: 70; anchors.verticalCenter: parent.verticalCenter }
                        DarkComboBox {
                            id: proxyFixedProxyCombo
                            width: 300; height: 36
                            model: []
                            onActivated: root.onFixedProxySelected()
                        }
                    }
                    GridLayout {
                        id: proxyManualRow
                        width: parent.width
                        visible: false
                        columns: 2
                        columnSpacing: 16
                        rowSpacing: 12
                        FormField { id: editorProxyHost; Layout.fillWidth: true; Layout.preferredWidth: 1; label: "Proxy Host" }
                        FormField { id: editorProxyPort; Layout.fillWidth: true; Layout.preferredWidth: 1; label: "Proxy Port" }
                        FormField { id: editorProxyUser; Layout.fillWidth: true; Layout.preferredWidth: 1; label: "Proxy User" }
                        FormField { id: editorProxyPassword; Layout.fillWidth: true; Layout.preferredWidth: 1; label: "Proxy Password" }
                    }
                }

                // --- Browser Overrides ---
                Column {
                    width: parent.width
                    spacing: 12
                    Rectangle { width: parent.width; height: 1; color: Theme.border }
                    Text { text: "Browser Overrides"; color: Theme.text; font.pixelSize: 16; font.bold: true }
                    Row {
                        width: parent.width
                        spacing: 20
                        DarkCheckBox { id: geoipCheckbox; text: "GeoIP (resolve at start)"; checked: false }
                        DarkCheckBox { id: humanizeCheckbox; text: "Humanize"; checked: false }
                        DarkCheckBox { id: loadImagesCheckbox; text: "Load images"; checked: true }
                    }
                    Row {
                        width: parent.width
                        visible: humanizeCheckbox.checked
                        spacing: 10
                        Text { text: "Preset"; color: Theme.muted; font.pixelSize: 13; width: 70; anchors.verticalCenter: parent.verticalCenter }
                        DarkComboBox {
                            id: humanPresetCombo
                            width: 180; height: 36
                            model: ["default", "careful"]
                        }
                    }
                    GridLayout {
                        width: parent.width
                        columns: 2
                        columnSpacing: 16
                        rowSpacing: 12
                        // Uniform preferredWidth + fillWidth forces equal column widths
                        FormField { id: editorLocale; Layout.fillWidth: true; Layout.preferredWidth: 1; label: "Locale"; placeholder: "en-US" }
                        FormField { id: editorTimezone; Layout.fillWidth: true; Layout.preferredWidth: 1; label: "Timezone"; placeholder: "America/New_York" }
                        FormField { id: editorUserAgent; Layout.fillWidth: true; Layout.preferredWidth: 1; label: "User Agent" }
                        FormField { id: editorCpu; Layout.fillWidth: true; Layout.preferredWidth: 1; label: "CPU Cores"; placeholder: "0 = inherit" }
                    }

                    // Platform + GPU Preset side by side
                    GridLayout {
                        width: parent.width
                        columns: 2
                        columnSpacing: 16
                        rowSpacing: 12
                        Row {
                            Layout.fillWidth: true
                            Layout.preferredWidth: 1
                            spacing: 10
                            Text { text: "Platform"; color: Theme.muted; font.pixelSize: 13; width: 70; anchors.verticalCenter: parent.verticalCenter }
                            DarkComboBox {
                                id: platformCombo
                                width: 180; height: 36
                                model: ["Inherit", "Windows", "Linux", "macOS"]
                            }
                        }
                        Row {
                            Layout.fillWidth: true
                            Layout.preferredWidth: 1
                            spacing: 10
                            Text { text: "GPU Preset"; color: Theme.muted; font.pixelSize: 13; width: 70; anchors.verticalCenter: parent.verticalCenter }
                            DarkComboBox {
                                id: gpuPresetCombo
                                width: 180; height: 36
                                model: gpuPresetModel
                                textRole: "name"
                                onActivated: function(index) {
                                    // 0 = Inherit, 1 = Custom, 2+ = concrete presets
                                    if (index === 0) {
                                        // Inherit: clear vendor/renderer (engine inherits)
                                        editorGpuVendor.text = ""
                                        editorGpuRenderer.text = ""
                                    } else if (index === 1) {
                                        // Custom: clear so user can type
                                        editorGpuVendor.text = ""
                                        editorGpuRenderer.text = ""
                                    } else {
                                        var presets = JSON.parse(profilesBridge.getGpuPresets())
                                        var preset = presets[index - 2]
                                        editorGpuVendor.text = preset.vendor
                                        editorGpuRenderer.text = preset.renderer
                                    }
                                }
                            }
                        }
                    }
                    FormField {
                        id: editorGpuVendor
                        width: parent.width
                        label: "GPU Vendor (clear to inherit)"
                        // Inherit -> disabled; Custom/preset -> enabled
                        enabled: gpuPresetCombo.currentIndex !== 0
                    }
                    FormField {
                        id: editorGpuRenderer
                        width: parent.width
                        label: "GPU Renderer (clear to inherit)"
                        enabled: gpuPresetCombo.currentIndex !== 0
                    }

                    // Screen Resolution
                    Column {
                        width: parent.width
                        spacing: 8
                        Text { text: "Screen"; color: Theme.muted; font.pixelSize: 13; font.bold: true }
                        Row {
                            width: parent.width
                            spacing: 10
                            DarkComboBox {
                                id: screenResCombo
                                width: 200; height: 36
                                textRole: "name"
                                model: screenResModel
                                onActivated: function(index) {
                                    // 0 = Inherit, 1 = Custom, 2+ = concrete preset
                                    if (index === 1) {
                                        // Custom: clear so user can type
                                        editorScreenWidth.text = ""
                                        editorScreenHeight.text = ""
                                    } else {
                                        var item = screenResModel.get(index)
                                        if (item.width > 0) {
                                            editorScreenWidth.text = String(item.width)
                                            editorScreenHeight.text = String(item.height)
                                        } else {
                                            // Inherit: clear
                                            editorScreenWidth.text = ""
                                            editorScreenHeight.text = ""
                                        }
                                    }
                                }
                            }
                            TextField {
                                id: editorScreenWidth
                                width: 80; height: 36
                                color: Theme.text; font.pixelSize: 13
                                // Custom only; Inherit and presets are read-only
                                readOnly: screenResCombo.currentIndex !== 1
                                enabled: screenResCombo.currentIndex === 1
                                placeholderText: "Width"; placeholderTextColor: Theme.dim
                                background: Rectangle { radius: 9; color: Theme.subtle; border.color: Theme.border }
                            }
                            TextField {
                                id: editorScreenHeight
                                width: 80; height: 36
                                color: Theme.text; font.pixelSize: 13
                                readOnly: screenResCombo.currentIndex !== 1
                                enabled: screenResCombo.currentIndex === 1
                                placeholderText: "Height"; placeholderTextColor: Theme.dim
                                background: Rectangle { radius: 9; color: Theme.subtle; border.color: Theme.border }
                            }
                        }
                    }
                }

                // Launch Args (CloakBrowser only)
                Column {
                    id: launchArgsSection
                    width: parent.width
                    spacing: 8
                    visible: false
                    Text { text: "Launch Args (CloakBrowser only, one per line)"; color: Theme.text; font.pixelSize: 13; font.bold: true }
                    Rectangle {
                        width: parent.width; height: 80; radius: 11; color: Theme.subtle; border.color: Theme.border
                        TextArea {
                            id: launchArgsField
                            anchors.fill: parent; anchors.margins: 10
                            color: Theme.text; font.pixelSize: 13; background: Item {}
                            placeholderText: "--disable-blink-features=AutomationControlled"
                            placeholderTextColor: Theme.dim; wrapMode: TextArea.Wrap
                        }
                    }
                }

                // Fingerprint Seed (CloakBrowser only)
                Row {
                    id: fingerprintSeedSection
                    width: parent.width
                    visible: false
                    spacing: 10
                    FormField { id: editorFpSeed; width: parent.width - 120; label: "Fingerprint Seed" }
                    PrimaryButton { width: 100; height: 40; text: "Random"; icon: "refresh"; onClicked: root.generateSeed() }
                }

                // Notes
                Column {
                    width: parent.width
                    spacing: 8
                    Text { text: "Notes"; color: Theme.text; font.pixelSize: 13; font.bold: true }
                    Rectangle {
                        width: parent.width; height: 70; radius: 11; color: Theme.subtle; border.color: Theme.border
                        TextArea {
                            id: editorNotes
                            anchors.fill: parent; anchors.margins: 10
                            color: Theme.text; font.pixelSize: 13; background: Item {}
                            placeholderText: "Profile notes..."; placeholderTextColor: Theme.dim; wrapMode: TextArea.Wrap
                        }
                    }
                }

                // --- Buttons ---
                Row {
                    spacing: 12
                    PrimaryButton {
                        width: 120
                        text: "Save"
                        icon: "save"
                        onClicked: {
                            profilesBridge.saveProfileData(root.editingProfile, root.collectProfileData())
                            profileDialog.close()
                        }
                    }
                    PrimaryButton { width: 110; text: "Vars"; secondary: true; onClicked: root.openVariablesModal(root.editingProfile) }
                    PrimaryButton { width: 120; text: "Cookies"; secondary: true; onClicked: root.openCookiesModal(root.editingProfile) }
                    PrimaryButton { width: 110; text: "Cancel"; secondary: true; onClicked: profileDialog.close() }
                }
            }
        }
        onOpened: {
            var resPresets = JSON.parse(profilesBridge.getScreenResolutionPresets())
            screenResModel.clear()
            screenResModel.append({ name: "Inherit", width: 0, height: 0 })
            screenResModel.append({ name: "Custom", width: 0, height: 0 })
            for (var i = 0; i < resPresets.length; i++)
                screenResModel.append(resPresets[i])
            var gpuPresets = JSON.parse(profilesBridge.getGpuPresets())
            gpuPresetModel.clear()
            gpuPresetModel.append({ name: "Inherit" })
            gpuPresetModel.append({ name: "Custom" })
            for (var j = 0; j < gpuPresets.length; j++)
                gpuPresetModel.append({ name: gpuPresets[j].name })
        }
    }

    Dialog {
        id: profileVarsDialog
        modal: true
        width: Math.min(760, root.width - 80)
        height: Math.min(620, root.height - 80)
        anchors.centerIn: Overlay.overlay
        padding: 0
        background: Rectangle { color: Theme.elevated; radius: 22; border.color: Theme.border }
        contentItem: Column {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 14
            Text { text: "Profile Variables: " + root.editingProfile; color: Theme.text; font.pixelSize: 22; font.bold: true }
            Rectangle {
                width: parent.width
                height: parent.height - 92
                radius: 14
                color: Theme.subtle
                border.color: Theme.border
                TextArea { id: profileVarsJson; anchors.fill: parent; anchors.margins: 12; color: Theme.text; font.family: "Consolas"; font.pixelSize: 12; background: Item {} }
            }
            Row {
                spacing: 10
                PrimaryButton { width: 120; text: "Save"; icon: "save"; onClicked: { profilesBridge.saveProfileVariables(root.editingProfile, profileVarsJson.text); profileVarsDialog.close() } }
                PrimaryButton { width: 110; text: "Cancel"; secondary: true; onClicked: profileVarsDialog.close() }
            }
        }
    }

    Dialog {
        id: profileCookiesDialog
        modal: true
        width: Math.min(840, root.width - 80)
        height: Math.min(660, root.height - 80)
        anchors.centerIn: Overlay.overlay
        padding: 0
        background: Rectangle { color: Theme.elevated; radius: 22; border.color: Theme.border }
        contentItem: Column {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 14
            Text { text: "Cookies JSON: " + root.editingProfile; color: Theme.text; font.pixelSize: 22; font.bold: true }
            Text { text: "Edit JSON array and save. Encrypted Chromium values may be read-only."; color: Theme.muted; font.pixelSize: 12 }
            Rectangle {
                width: parent.width
                height: parent.height - 122
                radius: 14
                color: Theme.subtle
                border.color: Theme.border
                TextArea { id: profileCookiesJson; anchors.fill: parent; anchors.margins: 12; color: Theme.text; font.family: "Consolas"; font.pixelSize: 12; background: Item {} }
            }
            Row {
                spacing: 10
                PrimaryButton { width: 120; text: "Refresh"; secondary: true; onClicked: profileCookiesJson.text = profilesBridge.getProfileCookiesJson(root.editingProfile) }
                PrimaryButton { width: 120; text: "Save"; icon: "save"; onClicked: { profilesBridge.saveProfileCookiesJson(root.editingProfile, profileCookiesJson.text); profileCookiesDialog.close() } }
                PrimaryButton { width: 110; text: "Cancel"; secondary: true; onClicked: profileCookiesDialog.close() }
            }
        }
    }

    Dialog {
        id: variablesDialog
        modal: true
        width: Math.min(860, root.width - 80)
        height: Math.min(560, root.height - 80)
        anchors.centerIn: Overlay.overlay
        padding: 0
        background: Rectangle { color: Theme.elevated; radius: 22; border.color: Theme.border }
        contentItem: Column {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 16
            RowLayout {
                width: parent.width
                height: 38
                Text { text: "Shared Variables"; color: Theme.text; font.pixelSize: 22; font.bold: true; Layout.fillWidth: true }
                PrimaryButton { Layout.preferredWidth: 104; text: "Close"; secondary: true; onClicked: variablesDialog.close() }
            }
            RowLayout {
                width: parent.width
                height: parent.height - 54
                spacing: 16
                ListView {
                    Layout.preferredWidth: 330
                    Layout.fillHeight: true
                    model: settingsBridge ? settingsBridge.variablesModel : null
                    spacing: 8
                    clip: true
                    delegate: Rectangle {
                        width: ListView.view.width
                        height: 54
                        radius: 12
                        color: Theme.subtle
                        border.color: Theme.border
                        Text { anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 24; text: "[" + model.type + "] " + model.key + ": " + model.value; color: Theme.muted; font.pixelSize: 12; elide: Text.ElideRight }
                        MouseArea { anchors.fill: parent; onClicked: { sharedKey.text = model.key; sharedType.text = model.type; sharedValue.text = settingsBridge.getVariable(model.key).value || "" } }
                    }
                }
                Column {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 14
                    FormField { id: sharedKey; width: parent.width; label: "Key" }
                    Row {
                        width: parent.width
                        spacing: 10
                        PrimaryButton { width: (parent.width - 20) / 3; text: "string"; secondary: sharedType.text !== "string"; onClicked: sharedType.text = "string" }
                        PrimaryButton { width: (parent.width - 20) / 3; text: "number"; secondary: sharedType.text !== "number"; onClicked: sharedType.text = "number" }
                        PrimaryButton { width: (parent.width - 20) / 3; text: "list"; secondary: sharedType.text !== "list"; onClicked: sharedType.text = "list" }
                    }
                    FormField { id: sharedType; visible: false; text: "string" }
                    Text { text: "Value"; color: Theme.text; font.pixelSize: 12; font.bold: true }
                    Rectangle { width: parent.width; height: 190; radius: 11; color: Theme.subtle; border.color: Theme.border
                        TextArea { id: sharedValue; anchors.fill: parent; anchors.margins: 10; color: Theme.text; placeholderText: "Value or one list item per line"; placeholderTextColor: Theme.dim; background: Item {} wrapMode: TextArea.Wrap; font.pixelSize: 13 }
                    }
                    Row {
                        spacing: 10
                        PrimaryButton { width: 130; text: "Save"; icon: "save"; onClicked: settingsBridge.saveVariable(sharedKey.text, sharedType.text, sharedValue.text) }
                        PrimaryButton { width: 110; text: "Delete"; danger: true; onClicked: settingsBridge.deleteVariable(sharedKey.text) }
                    }
                }
            }
        }
    }

    Menu {
        id: profileMenu
        MenuItem { text: "Profile settings"; onTriggered: root.openProfileModal(root.contextProfile) }
        MenuItem { text: "Open browser"; onTriggered: profilesBridge.startProfile(root.contextProfile) }
        MenuItem { text: "Variables"; onTriggered: root.openVariablesModal(root.contextProfile) }
        MenuItem { text: "Cookies"; onTriggered: root.openCookiesModal(root.contextProfile) }
        MenuItem { text: "Run selected scenario"; onTriggered: { scenariosBridge.setRunProfile(root.contextProfile); scenariosBridge.runSelected() } }
        MenuSeparator {}
        MenuItem { text: "Delete profile"; onTriggered: profilesBridge.deleteProfile(root.contextProfile) }
    }
}
