"""Cadastro de empresas e de usuários pela API."""
import pytest

EMPRESA = {"razao_social": "CADASTRO MANUAL LTDA", "cnpj": "04.252.011/0001-10", "regime_tributario": "SIMPLES_NACIONAL",
           "uf": "RJ", "cnae": "4530-7/03", "telefone": "(21) 3333-4444", "representante_legal": "Ana Teste"}


@pytest.fixture(scope="module")
def empresa(cliente, contador):
    r = cliente.post("/api/empresas", headers=contador, json=EMPRESA)
    assert r.status_code == 201, r.text
    return r.json()


def test_cria_empresa_normalizada(empresa):
    assert (empresa["cnpj"], empresa["cnae"], empresa["telefone"], empresa["anexo_simples"]) == \
        ("04252011000110", "4530703", "2133334444", "I")
    assert empresa["criado_em"]  # data de cadastro na lista


@pytest.mark.parametrize("campo,valor", [("cnae", "123"), ("uf", "ZZ"), ("telefone", "1234"), ("cnpj", "11111111111111")])
def test_empresa_invalida(cliente, contador, campo, valor):
    r = cliente.post("/api/empresas", headers=contador, json={**EMPRESA, "cnpj": "33.000.167/0001-01", campo: valor})
    assert r.status_code == 422 and campo in r.json()["campos"]


def test_nao_edita_para_cnpj_de_outra_empresa(cliente, contador, empresa):
    r = cliente.put(f"/api/empresas/{empresa['id']}", headers=contador, json={**EMPRESA, "cnpj": "11.222.333/0001-81"})
    assert r.status_code == 409 and "cnpj" in r.json()["campos"]


def test_analista_nao_edita_empresa(cliente, analista, empresa):
    assert cliente.put(f"/api/empresas/{empresa['id']}", headers=analista, json=EMPRESA).status_code == 403


def test_mudar_regime_desatualiza_simulacao(cliente, contador):
    emp = cliente.get("/api/empresas?busca=11222333000181", headers=contador).json()[0]
    pid = next(p["id"] for p in cliente.get("/api/planejamentos", headers=contador).json() if p["cnpj"] == emp["cnpj"])
    sim = cliente.post(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()

    corpo = {k: emp[k] for k in ("razao_social", "cnpj", "regime_tributario", "anexo_simples", "uf", "cnae", "atividade", "representante_legal", "telefone")}
    cliente.put(f"/api/empresas/{emp['id']}", headers=contador, json={**corpo, "representante_legal": "Outro Nome"})
    lista = cliente.get(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    assert next(s for s in lista if s["id"] == sim["id"])["desatualizada"] is False  # dado cadastral não muda o cálculo

    cliente.put(f"/api/empresas/{emp['id']}", headers=contador, json={**corpo, "uf": "MG"})
    lista = cliente.get(f"/api/planejamentos/{pid}/simulacoes", headers=contador).json()
    assert next(s for s in lista if s["id"] == sim["id"])["desatualizada"] is True
    cliente.put(f"/api/empresas/{emp['id']}", headers=contador, json=corpo)


def test_inativa_com_planejamento_reativa_e_exclui_sem(cliente, contador):
    e = cliente.post("/api/empresas", headers=contador, json={**EMPRESA, "razao_social": "TEMPORARIA", "cnpj": "60.746.948/0001-12"}).json()
    p = cliente.post("/api/planejamentos", headers=contador, json={
        "empresa_id": e["id"], "competencia_inicial": "2026-01", "competencia_final": "2026-01"})
    assert p.status_code == 201
    assert cliente.delete(f"/api/empresas/{e['id']}", headers=contador).status_code == 204
    assert not any(x["id"] == e["id"] for x in cliente.get("/api/empresas", headers=contador).json())
    todas = cliente.get("/api/empresas?ativas=false", headers=contador).json()
    assert next(x for x in todas if x["id"] == e["id"])["ativo"] is False
    assert cliente.post(f"/api/empresas/{e['id']}/reativar", headers=contador).json()["ativo"] is True

    livre = cliente.post("/api/empresas", headers=contador, json={**EMPRESA, "razao_social": "SEM PLANO", "cnpj": "00.000.000/0001-91"}).json()
    assert cliente.delete(f"/api/empresas/{livre['id']}", headers=contador).status_code == 204
    assert not any(x["id"] == livre["id"] for x in cliente.get("/api/empresas?ativas=false", headers=contador).json())


# ------------------------------------------------------------------ usuários


def login(cliente, usuario, senha):
    return cliente.post("/api/auth/login", json={"usuario": usuario, "senha": senha})


def test_ciclo_do_usuario(cliente, contador):
    r = cliente.post("/api/usuarios", headers=contador, json={"nome": "Nova Analista", "usuario": "nova.analista", "senha": "senha-forte", "perfil": "ANALISTA"})
    assert r.status_code == 201 and "senha_hash" not in r.json()
    u = r.json()
    assert login(cliente, "nova.analista", "senha-forte").status_code == 200

    base = {"nome": "Nova Analista", "perfil": "ANALISTA", "ativo": True}
    assert cliente.put(f"/api/usuarios/{u['id']}", headers=contador, json={**base, "senha": "outra-senha"}).status_code == 200
    assert login(cliente, "nova.analista", "senha-forte").status_code == 401
    assert login(cliente, "nova.analista", "outra-senha").status_code == 200

    assert cliente.put(f"/api/usuarios/{u['id']}", headers=contador, json={**base, "nome": "Sem Senha"}).status_code == 200
    assert login(cliente, "nova.analista", "outra-senha").status_code == 200  # sem senha nova, mantém

    token = login(cliente, "nova.analista", "outra-senha").json()["token"]
    assert cliente.put(f"/api/usuarios/{u['id']}", headers=contador, json={**base, "ativo": False}).status_code == 200
    assert login(cliente, "nova.analista", "outra-senha").status_code == 401
    assert cliente.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401  # sessão aberta cai


@pytest.mark.parametrize("corpo,campo", [
    ({"nome": "Xy", "usuario": "curta", "senha": "1234567", "perfil": "ANALISTA"}, "senha"),
    ({"nome": "Xy", "usuario": "com espaco", "senha": "12345678", "perfil": "ANALISTA"}, "usuario"),
    ({"nome": "Xy", "usuario": "valido", "senha": "12345678", "perfil": "CHEFE"}, "perfil"),
])
def test_usuario_invalido(cliente, contador, corpo, campo):
    r = cliente.post("/api/usuarios", headers=contador, json=corpo)
    assert r.status_code == 422 and campo in r.json()["campos"]


def test_login_duplicado(cliente, contador):
    r = cliente.post("/api/usuarios", headers=contador, json={"nome": "Dup", "usuario": "analista", "senha": "12345678", "perfil": "ANALISTA"})
    assert r.status_code == 409


def test_contador_nao_se_bloqueia(cliente, contador):
    eu = cliente.get("/api/auth/me", headers=contador).json()
    base = {"nome": eu["nome"], "perfil": "CONTADOR", "ativo": True}
    assert cliente.put(f"/api/usuarios/{eu['id']}", headers=contador, json={**base, "ativo": False}).status_code == 409
    assert cliente.put(f"/api/usuarios/{eu['id']}", headers=contador, json={**base, "perfil": "ANALISTA"}).status_code == 409


def test_analista_nao_gerencia_usuarios(cliente, analista):
    assert cliente.get("/api/usuarios", headers=analista).status_code == 403
    assert cliente.post("/api/usuarios", headers=analista, json={"nome": "Xy", "usuario": "xyz", "senha": "12345678", "perfil": "CONTADOR"}).status_code == 403
