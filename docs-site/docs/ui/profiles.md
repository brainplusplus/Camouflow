# Profiles

The **Profiles** page manages local browser profiles, tags, profile variables, cookies and batch scenario runs.

## Profile list

- **New Profile** creates an empty profile.
- **Import** opens bulk import.
- **Tags** opens tag management.
- Search filters by profile name, tags and proxy label.
- Each row can start/stop a browser session, open profile settings or delete the profile.
- Right-click a profile for quick actions: settings, open browser, variables, cookies, run selected scenario or delete.

## Bulk import

Use **Import** to add many profiles at once:

- Paste profiles, one per line.
- Set the account parse template, for example:

```text
{email};{password};{secret_key};{extra};{twofa_url}
```

- Set an optional default tag.
- Pick an optional proxy pool. CamouFlow assigns the first free proxy from that pool to each imported profile.

Imported fields are saved as profile variables and can be used in scenarios as `{{email}}`, `{{password}}`, etc.

## Profile settings

The settings dialog edits:

- name
- tag
- proxy host / port / user / password
- per-profile browser overrides: locale, timezone, user agent, WebGL/GPU vendor, CPU cores

## Variables and cookies

From profile settings or the context menu:

- **Vars** edits profile variables as a JSON object.
- **Cookies** reads profile cookies from local browser storage and saves a JSON cookie array back through the browser context.

Chromium encrypted cookie values can be displayed as `<encrypted>` and may not be reusable.

## Run scenario for tag

The bottom panel runs a selected scenario for profiles matching a tag:

- **Tag** selects the profile tag. `All tags` runs across all profiles.
- **Scenario** selects the scenario.
- **Max** limits the number of profiles processed.
- **Run for tag** starts the batch run.

## Shared variables

The **Variables** button opens the shared variables editor. Shared variables are available to all profiles and scenarios.
