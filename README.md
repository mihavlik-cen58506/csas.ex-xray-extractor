# Xray Test Count Extractor

Keboola komponenta pro extrakci počtu testů z Xray Cloud API.

## Funkcionalita

Komponenta načítá vstupní tabulku s parametry, volá Xray GraphQL API a vrací počet nalezených testů pro každý řádek.

## Konfigurace

### Parametry

- **#xray_client_id** (povinný) - Xray Cloud Client ID
- **#xray_client_secret** (povinný) - Xray Cloud Client Secret
- **input_column_name** (povinný) - Název sloupce s parametry
- **output_column_name** (povinný) - Název sloupce pro výstup
- **debug** (volitelný) - Debug logování (default: false)
- **incremental** (volitelný) - Inkrementální načítání (default: false)

### Vstupní data

Vstupní tabulka musí obsahovat:

**Sloupec s parametry** (podle `input_column_name`):
JSON array se 3 parametry: `[project_id, folder_path, jql_query]`

**Sloupec AUTO_DATA_AUTOMATICALLY**:
- **Y** - provede se GraphQL dotaz
- **N** nebo prázdné - řádek se přeskočí (výchozí)

**Příklady:**
```
 input_column
 ["10074", "/CoE Testy/Adam - Test Import", ""]
 ["12345", "ui/login", "assignee = currentUser()"]
 ["45678", "", "project = DEMO AND status = Open"]
 ["78910", "api/endpoints", "status IN ('Open', 'Done')"]
```

**Parametry JSON:**
- **project_id** - Xray/Jira Project ID (povinný)
- **folder_path** - Cesta ke složce v Xray (volitelný, použijte prázdný string "")
- **jql_query** - JQL dotaz (volitelný, použijte prázdný string "")

## Výstup

Komponenta přidá nový sloupec s počtem testů:
- **Úspěch**: Číselná hodnota (např. 42)
- **Chyba**: NULL hodnota (chyby jsou logovány)

## GraphQL dotazy

Komponenta vytváří tyto dotazy podle parametrů:

```graphql
# Všechny parametry
query {
  getTests(
    projectId: "10074"
    folder: { path: "/CoE Testy/Adam - Test Import" }
    jql: "status = Open"
    limit: 100
  ) {
    total
  }
}

# Pouze project ID
query {
  getTests(projectId: "10074", limit: 100) {
    total
  }
}
```

## Development

```bash
git clone https://github.com/mihavlik-cen58506/csas.ex-xray-extractor
cd csas.ex-xray-extractor
docker-compose build
docker-compose run --rm dev
```

Testy:
```bash
docker-compose run --rm test
```