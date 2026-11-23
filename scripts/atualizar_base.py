import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
import urllib.error
import urllib.request
import urllib.parse

CEP_ALVO = "13255280"
CEP_FORMATADO = "13255-280"
LOJA_NOME = "Itatiba"
ARQUIVO_SAIDA = os.path.join("data", "produtos.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Origin": "https://www.tendaatacado.com.br",
    "Referer": "https://www.tendaatacado.com.br/",
}

ENDPOINTS_JSON = [
    "https://api.tendaatacado.com.br/api/public/store/search?query={query}&zipCode={cep}&page=1&limit=50",
    "https://api.tendaatacado.com.br/api/public/store/search?query={query}&cep={cep}&page=1&limit=50",
    "https://api.tendaatacado.com.br/api/public/store/search?query={query}&postalCode={cep}&page=1&limit=50",
]

TERMOS_BUSCA = [
    # Mercearia básica e grãos
    "arroz", "feijao", "cafe", "oleo", "azeite", "acucar", "sal",
    "farinha", "fuba", "polvilho", "fermento", "milho", "aveia", "granola",
    # Massas, molhos e conservas
    "macarrao", "miojo", "molho", "extrato de tomate", "maionese", "ketchup",
    "mostarda", "azeitona", "milho verde", "ervilha", "atum", "sardinha",
    # Laticínios, frios e padaria
    "leite", "leite condensado", "creme de leite", "queijo", "mussarela",
    "presunto", "requeijao", "margarina", "manteiga", "iogurte", "pao",
    # Carnes e congelados
    "frango", "carne", "linguica", "salsicha", "hamburguer", "nuggets",
    "lasanha", "pizza", "batata congelada",
    # Biscoitos, doces e matinais
    "biscoito", "bolacha", "chocolate", "bombom", "achocolatado", "cereal",
    "geleia", "mel", "bala", "chiclete",
    # Bebidas
    "refrigerante", "suco", "agua", "agua com gas", "energetico", "cha",
    "cerveja", "vinho", "vodka", "cachaca", "whisky",
    # Limpeza
    "sabao", "sabao em po", "detergente", "amaciante", "agua sanitaria",
    "desinfetante", "limpador", "esponja", "saco de lixo", "pano de limpeza",
    # Higiene pessoal e perfumaria
    "papel higienico", "sabonete", "shampoo", "condicionador", "creme dental",
    "escova de dente", "desodorante", "absorvente", "fralda", "lenco umedecido",
    # Utilidades e pet
    "papel toalha", "papel aluminio", "filme pvc", "lampada", "pilha",
    "racao", "petisco", "areia gato",
]


def _extrair_itens(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for chave in ("products", "items", "data", "results", "content"):
            valor = payload.get(chave)
            if isinstance(valor, list):
                return valor
            if isinstance(valor, dict):
                for subchave in ("products", "items", "list", "content"):
                    if isinstance(valor.get(subchave), list):
                        return valor[subchave]
    return []


def _parse_preco(valor):
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str):
        limpo = re.sub(r"[^\d,.]", "", valor).replace(",", ".")
        try:
            return float(limpo)
        except ValueError:
            return 0.0
    return 0.0


def _extrair_json_embutido_html(html_texto):
    match_next = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html_texto, re.DOTALL)
    if match_next:
        try:
            return json.loads(match_next.group(1))
        except Exception:
            pass

    for match in re.finditer(r'<script[^>]*>(.*?)</script>', html_texto, re.DOTALL):
        trecho = match.group(1).strip()
        if "products" in trecho and "{" in trecho:
            idx = trecho.find("{")
            if idx != -1:
                try:
                    return json.loads(trecho[idx:])
                except Exception:
                    continue
    return None


def buscar_produtos_tenda(cep: str):
    """
    Consulta o endpoint ajustado com 'query=' e, se necessário, tenta extrair
    dados embutidos da página de busca do Tenda para o CEP informado.
    Retorna lista padronizada no formato esperado pelo Index.html.
    """
    produtos_coletados = []
    vistos = set()

    endpoint_ativo = None
    usar_fallback_html = False
    erros_registrados = 0

    for termo in TERMOS_BUSCA:
        query = urllib.parse.quote(termo)
        payload = None

        if not usar_fallback_html:
            candidatos = [endpoint_ativo] if endpoint_ativo else ENDPOINTS_JSON
            for template in candidatos:
                url = template.format(query=query, cep=cep)
                req = urllib.request.Request(url, headers=HEADERS)
                try:
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        if resp.status != 200:
                            continue
                        payload = json.loads(resp.read().decode("utf-8"))
                        endpoint_ativo = template
                        break
                except urllib.error.HTTPError as e:
                    if erros_registrados < 5:
                        corpo = ""
                        try:
                            corpo = e.read().decode("utf-8", errors="ignore")[:180].strip()
                        except Exception:
                            corpo = ""
                        print(f"[Aviso] '{termo}' em {url} -> HTTP {e.code} {e.reason} {corpo}")
                        erros_registrados += 1
                except Exception as e:
                    if erros_registrados < 5:
                        print(f"[Aviso] Falha ao consultar termo '{termo}': {e}")
                        erros_registrados += 1

            if endpoint_ativo is None and termo == "feijao":
                usar_fallback_html = True

        if usar_fallback_html or payload is None:
            url_html = f"https://www.tendaatacado.com.br/busca?q={query}"
            headers_html = dict(HEADERS)
            headers_html["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            req_html = urllib.request.Request(url_html, headers=headers_html)
            try:
                with urllib.request.urlopen(req_html, timeout=20) as resp:
                    if resp.status == 200:
                        html_str = resp.read().decode("utf-8", errors="ignore")
                        payload = _extrair_json_embutido_html(html_str)
            except Exception as e:
                if erros_registrados < 6:
                    print(f"[Aviso] Fallback HTML falhou para '{termo}': {e}")
                    erros_registrados += 1

        itens = _extrair_itens(payload)

        for item in itens:
            if not isinstance(item, dict):
                continue
            ean = str(item.get("ean") or item.get("barcode") or item.get("gtin") or "").strip()
            nome = str(item.get("name") or item.get("title") or "").strip()
            if not nome:
                continue

            chave = ean if ean else nome.lower()
            if chave in vistos:
                continue
            vistos.add(chave)

            preco_comum = _parse_preco(item.get("price") or item.get("regularPrice") or item.get("listPrice") or 0)
            preco_cartao = _parse_preco(
                item.get("cardPrice")
                or item.get("tendaCardPrice")
                or item.get("promotionalPrice")
                or preco_comum
            )
            regra = str(item.get("promotionLabel") or item.get("badge") or "").strip()

            if preco_comum > 0:
                produtos_coletados.append({
                    "id": len(produtos_coletados) + 1,
                    "ean": ean,
                    "nome": nome,
                    "comum": round(preco_comum, 2),
                    "cartao": round(preco_cartao if preco_cartao > 0 else preco_comum, 2),
                    "regra": regra
                })

        time.sleep(0.8)

    return produtos_coletados


def main():
    os.makedirs("data", exist_ok=True)
    fuso_br = timezone(timedelta(hours=-3))
    agora = datetime.now(fuso_br).isoformat(timespec="seconds")

    print(f"Iniciando coleta para Loja {LOJA_NOME} (CEP {CEP_FORMATADO})...")
    produtos = buscar_produtos_tenda(CEP_ALVO)

    if not produtos:
        print("Nenhum produto retornado na coleta. Mantendo base anterior intacta.")
        return

    saida = {
        "atualizadoEm": agora,
        "loja": LOJA_NOME,
        "cep": CEP_FORMATADO,
        "total": len(produtos),
        "produtos": produtos
    }

    with open(ARQUIVO_SAIDA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)

    print(f"Sucesso! {len(produtos)} produtos salvos em {ARQUIVO_SAIDA}.")


if __name__ == "__main__":
    main()
