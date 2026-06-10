# Apex Adventure Alliance — Brand Styles

Source: https://apexadventurealliance.com/ (scraped 2026-05-13)
Theme: Catch Themes "Adventurous" v3.6, customized with sage green

---

## Colors

| Role | Hex | Usage |
|------|-----|-------|
| Primary CTA / active | `#9bc23c` | Buttons, active states, accents |
| Primary link / border accent | `#7c9b30` | Links, top borders on dropdowns, hover |
| Button hover / pressed | `#87ae28` | Hover state on CTA buttons |
| Heading text | `#222` | h1–h6 |
| Body text | `#404040` | Paragraphs |
| Secondary text / meta | `#757575` | Captions, dates, labels |
| Form input text | `#7c7c7c` | Input fields |
| Page background | `#f9f9f9` | Body, featured post areas |
| Content background | `#fff` | White card / content areas |
| Borders / dividers | `#eee` | Rule lines, card borders |
| Footer / nav background | `#000` | Footer bar, secondary nav |
| Aside post accent | `#d2e0f9` | Aside-format post background |

---

## Typography

- **Font family:** `sans-serif, Arial` (system font stack, no custom webfont)
- **Heading sizes:** h1 24px / h2 22px / h3 20px / h4 18px / h5 16px / h6 14px
- **Body size:** 14–16px
- **Line height:** 1.65 (body), 1.6–1.7 (content)

---

## Buttons

**Primary (CTA)**
```css
background: #9bc23c;
color: #fff;
border: 2px solid #fff;
border-radius: 5px;
padding: 10px 25px;
font-size: 22px;
box-shadow: 0 -3px 0 rgba(0,0,0,0.2) inset;
transition: 0.2s ease-in-out;
```
Hover: `background: #87ae28; box-shadow: 0 3px 0 rgba(0,0,0,0.2) inset;`

**Outline**
```css
color: #9bc23c;
background: transparent;
border: 2px solid #9bc23c;
border-radius: 5px;
```
Hover: `background: #87ae28; color: #fff;`

---

## Shadows & Borders

```css
/* Card / panel shadow */
box-shadow: 0 0 7px rgba(0,0,0,0.1);

/* Dropdown / elevated shadow */
box-shadow: 0 2px 5px rgba(0,0,0,0.1);

/* Standard border */
border: 1px solid #eee;

/* Green top accent (dropdowns, mobile nav) */
border-top: 3px solid #7c9b30;
```

---

## Spacing

- Content padding: 20–30px
- Button padding: 10px 25px (primary), 5px 20px (small)
- Border-radius: **5px** (buttons, cards — consistent throughout)
- Max content width: 1250px

---

## Logo Files

- Primary: `ApexPrimaryLogoFinal.png` (circular badge)
- Rope variant: `cropped-rope-logo-*.png` (used as favicon)
