# Browser

The **Browser** page configures global browser-engine defaults.

## Engines

CamouFlow supports:

- **Camoufox**
- **CloakBrowser**

The selected engine is stored globally and can be overridden per profile.

## Main groups

- **Execution**: window/headless mode and humanization.
- **Operating Systems**: Camoufox OS fingerprint pool.
- **Cloak Fingerprint**: CloakBrowser platform and fingerprint seed.
- **Locale & Timezone**: browser locale and timezone overrides.
- **Storage / Runtime**: persistent context, cache and Cloak backend.
- **Window Size**: viewport and screen defaults.
- **Runtime Protection**: WebRTC, image, WebGL and COOP restrictions.
- **Window Overrides**: raw Camoufox `window_overrides` JSON.
- **Navigator**: user agent, CPU cores and raw navigator overrides.
- **WebGL / GPU**: vendor and renderer overrides.
- **Addons / Launch**: Camoufox fonts/addons/exclude-addons or CloakBrowser extension paths/launch args.

## Actions

- **Save** persists the active engine settings.
- **Reset** restores recommended defaults for the active engine.
