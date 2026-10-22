# PDF font assets

The wordbook PDF renderer bundles two SIL Open Font License 1.1 fonts so server-side PDFs can
contain both Chinese definitions and IPA/phonetic text without relying on host fonts.

| File | Role | SHA-256 |
|---|---|---|
| `NotoSans-Regular.ttf` | Latin, IPA, headwords, English definitions | `b85c38ecea8a7cfb39c24e395a4007474fa5a4fc864f6ee33309eb4948d232d5` |
| `NotoSansSC-Regular.ttf` | Simplified Chinese definitions and translations | `9d723b2ef771739d7e636c47af831542595b3eeeaa25735d2be7452da8d6555a` |

Sources:

- Noto Sans Latin: `https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf`
- Noto Sans SC variable source: `https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/Variable/TTF/Subset/NotoSansSC-VF.ttf`
- The SC static instance was generated from that variable source before being committed here.
- The upstream variable source used for the static instance had SHA-256
  `a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da`.

`OFL.txt` is the license supplied with these Noto fonts and must remain alongside them. The fonts are
not sourced from user uploads or undocumented third-party collections.
