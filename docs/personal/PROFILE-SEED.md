# Local profile import

A seed is a UTF-8 JSON object with exactly `version` and `records`. Version is `1`; records is an array of at most 50 objects, each with exactly `category`, `kind`, and `value`. Supported categories are `basics`, `school_work`, `preferences`, and `notes`. Kind is at most 40 characters; value is at most 300. Values must be single-line, whitespace-normalized text. Kinds must be unique within each category. Example using synthetic data:

```json
{"version":1,"records":[{"category":"basics","kind":"name","value":"Example"},{"category":"preferences","kind":"answer style","value":"Concise"}]}
```

The seed must contain only owner-approved material. Do not include credentials, raw conversations, health information, or other people's private information. Structural and keyword checks are safeguards, not a guarantee that text contains no sensitive data. Shortcut descriptions are profile facts only: they never create shortcuts or perform actions.

After the app has initialized its existing development profile, the owner can run:

```sh
/usr/bin/python3 "/path/to/ATLAS.app/Contents/Resources/memory_seed.py" "/path/to/private-profile.json"
```

The tool displays every proposed addition or skipped existing category/kind and asks for `IMPORT`. Return cancels. It writes only the existing local `~/.config/atticus-personal-dev/me.json` using its shared lock and atomic replacement; it makes no provider call. Existing same-kind records are never overwritten. A store change after preview cancels the import. Imported records appear as owner-confirmed (`source: you`) and have a `seed-` ID as provenance. Unsupported legacy or unknown store structures are refused rather than migrated. Keep the private seed outside source control and do not share it without separate authorization.
