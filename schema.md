# Course Catalog Data Schema

Based on Marinovic (2026) "What Universities (Say They) Teach"

## Record Fields

| Field | Type | Description |
|-------|------|-------------|
| university | string | Short name identifier (e.g., "stanford", "umich") |
| academic_year | string | Academic year start (e.g., "2001", "2024") |
| academic_year_label | string | Full label (e.g., "2001-2002", "2024-2025") |
| department_code | string | Department or subject code |
| course_number | string | Course number (e.g., "101", "CS106A") |
| title | string | Course title |
| description | string | Full course description |
| broad_area | string | Humanities / Social Sciences / STEM / Medical Sciences / Professional / Other |
| level | string | undergraduate (course num < 200) or graduate (>= 200) |
| progressive_signal | boolean | Match on progressive keyword list |
| western_canon_signal | boolean | Match on Western canon keyword list |
| climate_narrow_signal | boolean | Match on narrow climate keyword list |
| climate_broad_signal | boolean | Match on broad climate/sustainability keyword list |
| cross_listed | boolean | Whether this record is a cross-listed duplicate |
| deduplicated | boolean | Whether this is the canonical record after dedup |

## Progressive Keyword List (Table 2 in paper)

### Diversity & Inclusion
diversity, diverse, inclusion, inclusive, belonging, DEI

### Race & Racism
race, racial, racism, racist, anti-racist, antiracist, racialized, white supremacy, white privilege, whiteness, BIPOC, people of color, Black lives, critical race

### Gender & Sexuality
gender, gendered, feminist, feminism, sexism, patriarchy, misogyny, queer, LGBTQ, transgender, nonbinary, intersex, sexuality, heteronormativity

### Equity & Social Justice
equity, equitable, social justice, injustice, oppression, oppressive, liberation, decolonize, decolonial, colonialism, colonial, postcolonial, settler colonialism

### Identity Politics
identity, identities, positionality, intersectionality, privilege, marginalized, marginalization, underrepresented, allyship

### Related Terms
indigenous, Native American, Latinx, Chicano, Chicana, diaspora, reparations, microaggression, implicit bias, systemic racism

## Western Canon Keyword List (Table 3 in paper)

### Tradition Framing
western civilization, western tradition, western thought, great books, liberal arts tradition

### Classical Antiquity
ancient Greece, ancient Rome, Greek philosophy, Roman law, classical antiquity, Greco-Roman

### Historical Periods
Renaissance, Enlightenment, medieval philosophy, Reformation

### Canonical Authors
Shakespeare, Plato, Aristotle, Homer, Dante, Virgil, Milton, Cicero, Socrates, Augustine, Aquinas, Machiavelli, Hobbes, Descartes, Kant, Hegel, Locke, Tocqueville, Montesquieu

### Canonical Texts
Bible, biblical, Iliad, Odyssey, Aeneid, Divine Comedy, Canterbury Tales, Leviathan, Federalist

### Classical Markers
classics, classical

## Area Classification

- **Humanities**: Literature, Languages, History, Philosophy, Art History, Music, Theater, Religion
- **Social Sciences**: Economics, Political Science, Sociology, Psychology, Anthropology, Geography, Communication
- **STEM**: CS, Math, Statistics, Physics, Chemistry, Biology, Engineering (all branches), Earth Sciences
- **Medical Sciences**: Medicine, Nursing, Public Health, Biomedical (at institutions with medical schools)
- **Professional**: Law, Business/MBA, Education, Public Policy, Social Work, Architecture
- **Other**: Interdisciplinary, Area Studies, Language Programs, Writing, Overseas, uncategorized

## File Format

Data stored as CSV per university per year:
`data/{short_name}/{short_name}_{year}.csv`

Summary statistics per university:
`data/{short_name}/{short_name}_summary.csv`

Columns: university, academic_year, total_courses, progressive_count, progressive_pct, canon_count, canon_pct, climate_narrow_count, climate_narrow_pct, climate_broad_count, climate_broad_pct
