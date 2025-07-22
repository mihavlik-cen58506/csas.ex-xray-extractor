XRay Extractor
=============

Keboola component pro extrakci počtu testů z Xray Cloud API pomocí dynamických parametrů.

Functionality Notes
===================

Komponenta načítá CSV soubor s JSON parametry pro každý řádek, volá Xray GraphQL API a vrací počet nalezených testů.

Prerequisites
=============

- Xray Cloud API přihlašovací údaje (Client ID a Client Secret)
- Správně nakonfigurovaná vstupní a výstupní tabulka v Keboole

Features
========

| **Feature**             | **Description**                               |
|-------------------------|-----------------------------------------------|
| Dynamické parametry     | Každý řádek může mít jiné project/folder/JQL |
| GraphQL API             | Používá Xray Cloud GraphQL endpoint          |
| Error handling          | Robustní zpracování chyb a retry logika      |
| Incremental Loading     | Podporuje inkrementální načítání             |
| Debug mode              | Rozšířené logování pro debugging             |

Configuration
=============

## Parametry komponenty

### input_column_name
**Povinný** - Název sloupce ve vstupní tabulce obsahující JSON pole s parametry.

### output_column_name  
**Povinný** - Název sloupce do kterého se uloží počet nalezených testů.

### #xray_client_id
**Povinný** - Xray Cloud Client ID pro autentifikaci.

### #xray_client_secret
**Povinný** - Xray Cloud Client Secret pro autentifikaci.

### debug
**Volitelný** (default: false) - Zapne rozšířené debug logování.

### incremental
**Volitelný** (default: false) - Zapne inkrementální načítání.

## Formát vstupních dat

Každý řádek ve vstupní tabulce musí obsahovat JSON pole se třemi parametry ve správném CSV formátu.

### CSV formát (s escapovanými uvozovkami):
```csv
input_column,description
"[""PROJ-123"", ""ui/login"", ""assignee = currentUser()""]",Login tests
"[""PROJ-456"", """", ""project = DEMO AND status = Open""]",Demo tests  
"[""PROJ-789"", ""api/endpoints"", """"]",API tests
"[""PROJ-999"", """", """"]",All project tests
```

### JSON struktura (po parsování):
```json
["PROJECT_ID", "folder/path", "jql query"]
```

### Příklady hodnot:
- `["PROJ-123", "ui/login", "assignee = currentUser()"]` - všechny parametry
- `["PROJ-456", "", "project = DEMO AND status = Open"]` - bez folder  
- `["PROJ-789", "api/endpoints", ""]` - bez JQL
- `["PROJ-999", "", ""]` - jen project ID

**Poznámka**: V CSV jsou uvozovky uvnitř hodnoty escapované zdvojením `""`. Po načtení komponenta automaticky parsuje JSON a získá správné hodnoty.

## Mapování tabulek

### Vstupní tabulka
Musí obsahovat sloupec s JSON parametry podle `input_column_name`.

### Výstupní tabulka
Komponenta vytvoří výstupní tabulku s původními sloupci + nový sloupec podle `output_column_name` obsahující počet testů.

Output
======

Pro každý řádek vrací:
- **Úspěch**: Číselnou hodnotu s počtem nalezených testů (např. `42`)
- **Chyba parsování**: `PARSE_ERROR: error message`
- **API chyba**: `API_ERROR: error message`
- **Prázdný vstup**: `ERROR: Empty input data`

## GraphQL dotazy

Komponenta vytváří tyto GraphQL dotazy podle vstupních parametrů:

```graphql
# Všechny parametry
query {
  getTests(
    projectId: "PROJ-123", 
    folder: {path: "ui/login"}, 
    jql: "assignee = currentUser()", 
    limit: 100
  ) {
    total
  }
}

# Jen project + JQL
query {
  getTests(
    projectId: "PROJ-456", 
    jql: "project = DEMO", 
    limit: 100
  ) {
    total
  }
}

# Jen project ID
query {
  getTests(projectId: "PROJ-999", limit: 100) {
    total
  }
}
```

Development
-----------

Pro lokální vývoj:

```bash
git clone https://github.com/mihavlik-cen58506/csas.ex-xray-extractor csas.ex-xray-extractor
cd csas.ex-xray-extractor
docker-compose build
docker-compose run --rm dev
```

Pro spuštění testů:

```bash
docker-compose run --rm test
```

Integration
===========

Pro nasazení do Kebooly viz [deployment dokumentace](https://developers.keboola.com/extend/component/deployment/).