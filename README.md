# Xray Test Count Extractor

Keboola komponenta pro extrakci počtu testů z Xray Cloud API.

## Funkcionalita

Komponenta načítá vstupní tabulku s parametry, volá Xray GraphQL API a vrací počty nalezených testů do dvou výstupních sloupců pro každý řádek. Pro každý řádek s flagom `AUTE_DATA_AUTOMATICALLY = "Y"` se provedou dva nezávislé API dotazy.

## Konfigurace

### Parametry

- **#xray_client_id** (povinný) - Xray Cloud Client ID
- **#xray_client_secret** (povinný) - Xray Cloud Client Secret
- **input_column_name** (povinný) - Název prvního vstupního sloupce s parametry
- **output_column_name** (povinný) - Název prvního výstupního sloupce
- **input_column_name_2** (povinný) - Název druhého vstupního sloupce s parametry
- **output_column_name_2** (povinný) - Název druhého výstupního sloupce
- **debug** (volitelný) - Debug logování (default: false)
- **incremental** (volitelný) - Inkrementální načítání (default: false)

### Vstupní data

Vstupní tabulka musí obsahovat:

**Sloupce s parametry** (podle `input_column_name` a `input_column_name_2`):
Každý sloupec obsahuje JSON array se 3 parametry: `[project_id, folder_path, jql_query]`

**Sloupec AUTO_DATA_AUTOMATICALLY**:
- **Y** - provede se GraphQL dotaz pro oba sloupce
- **N** nebo prázdné - řádek se přeskočí (výchozí)

**Příklady:**
```
 input_column                                  | input_column_2
 ["10074", "/CoE Testy/Adam - Test Import", ""] | ["10074", "/CoE Testy/Executions", ""]
 ["12345", "ui/login", "assignee = currentUser()"] | ["12345", "ui/results", "status = Done"]
 ["45678", "", "project = DEMO AND status = Open"] | ["45678", "", "project = DEMO AND type = Execution"]
 ["78910", "api/endpoints", "status IN ('Open', 'Done')"] | ["78910", "api/results", "created >= -30d"]
```

**Parametry JSON:**
- **project_id** - Xray/Jira Project ID (povinný)
- **folder_path** - Cesta ke složce v Xray (volitelný, použijte prázdný string "")
- **jql_query** - JQL dotaz (volitelný, použijte prázdný string "")

## Výstup

Komponenta přidá dva nové sloupce s počty testů:
- **Úspěch**: Číselná hodnota (např. 42) v příslušném výstupním sloupci
- **Chyba**: NULL hodnota (chyby jsou logovány)
- Pokud je vstupní sloupec prázdný, výstupní sloupec bude NULL

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