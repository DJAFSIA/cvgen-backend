import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import stripe

import app.routers.billing as rb
from app.core.config import settings
from app.models.utilisateur import Utilisateur
from app.services import billing
from conftest import code


def utilisateur(db, u):
    db.expire_all()
    return db.query(Utilisateur).filter(Utilisateur.id == u.id).first()


# ----------------------------------------------------------------- Mobile Money
@pytest.fixture
def flutterwave(monkeypatch):
    monkeypatch.setattr(settings, "FLUTTERWAVE_SECRET_KEY", "FLWSECK_TEST-fake")
    monkeypatch.setattr(settings, "FLUTTERWAVE_WEBHOOK_HASH", "hash-secret")
    etat = {"amount": 3000, "status": "successful", "currency": "XAF", "tx_ref": None}
    vrai = httpx.AsyncClient

    def repondre(req):
        if req.method == "POST" and req.url.path == "/v3/payments":
            corps = json.loads(req.content)
            etat["tx_ref"] = corps["tx_ref"]
            assert corps["amount"] == 3000 and corps["currency"] == "XAF"
            return httpx.Response(200, json={"status": "success", "data": {"link": "https://checkout.flutterwave.com/pay/x"}})
        if req.url.path.endswith("/verify"):
            return httpx.Response(200, json={"status": "success", "data": {
                "id": 777, "tx_ref": etat["tx_ref"], "status": etat["status"],
                "amount": etat["amount"], "currency": etat["currency"]}})
        return httpx.Response(404, json={"status": "error"})

    monkeypatch.setattr(rb.httpx, "AsyncClient", lambda **kw: vrai(transport=httpx.MockTransport(repondre), **kw))
    return etat


def test_momo_paiement_valide_et_idempotent(client, db, make_user, flutterwave):
    u, h = make_user()
    assert client.post("/billing/momo/checkout", json={"devise": "XAF"}, headers=h).status_code == 200
    r = client.post("/billing/momo/confirm", json={"transaction_id": "777"}, headers=h).json()
    assert r["plan"] == "pro" and r["statut"] == "paid"
    fin = utilisateur(db, u).plan_expire_le
    assert 29 <= (fin - datetime.now(timezone.utc)).days <= 30

    client.post("/billing/momo/confirm", json={"transaction_id": "777"}, headers=h)
    assert client.post("/billing/momo/webhook", json={"data": {"id": 777}}, headers={"verif-hash": "hash-secret"}).status_code == 200
    assert utilisateur(db, u).plan_expire_le == fin  # jamais credite deux fois


def test_momo_montant_insuffisant_refuse(client, make_user, flutterwave):
    _, h = make_user()
    client.post("/billing/momo/checkout", json={"devise": "XAF"}, headers=h)
    flutterwave["amount"] = 100
    r = client.post("/billing/momo/confirm", json={"transaction_id": "777"}, headers=h).json()
    assert r["plan"] == "free" and r["statut"] == "pending"


def test_momo_devise_et_faux_webhook_refuses(client, make_user, flutterwave):
    _, h = make_user()
    assert client.post("/billing/momo/checkout", json={"devise": "EUR"}, headers=h).status_code == 400
    assert client.post("/billing/momo/webhook", json={"data": {"id": 777}}, headers={"verif-hash": "faux"}).status_code == 401


def test_momo_passes_cumules(client, db, make_user, flutterwave):
    u, h = make_user()
    for _ in range(2):
        client.post("/billing/momo/checkout", json={"devise": "XAF"}, headers=h)
        client.post("/billing/momo/confirm", json={"transaction_id": "777"}, headers=h)
    assert 59 <= (utilisateur(db, u).plan_expire_le - datetime.now(timezone.utc)).days <= 60


# ----------------------------------------------------------------- Stripe
FIN = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())


@pytest.fixture
def faux_stripe(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_fake")
    appels = {"subs_existants": [], "cus": f"cus_{uuid.uuid4().hex[:12]}"}

    def f(nom, retour):
        def appel(*args, api_key=None, **kwargs):
            assert api_key == "sk_test_fake"
            appels[nom] = kwargs
            return retour(*args, **kwargs)
        return appel

    monkeypatch.setattr(stripe.Customer, "create", f("customer", lambda **kw: {"id": appels["cus"]}))
    monkeypatch.setattr(stripe.checkout.Session, "create", f("session", lambda **kw: {"url": "https://checkout.stripe.com/c/pay/x"}))
    monkeypatch.setattr(stripe.Subscription, "list", f("list", lambda **kw: {"data": appels["subs_existants"]}))
    monkeypatch.setattr(stripe.Subscription, "retrieve", f("sub", lambda sid, **kw: {
        "id": sid, "status": "active", "items": {"data": [{"current_period_end": FIN}]}}))
    monkeypatch.setattr(stripe.Charge, "retrieve", f("charge", lambda cid, **kw: {"id": cid, "customer": appels["cus"]}))
    return appels


def session_de(u, monkeypatch, autre=False):
    monkeypatch.setattr(stripe.checkout.Session, "retrieve", lambda sid, api_key=None: {
        "id": sid, "client_reference_id": "autre" if autre else str(u.id),
        "status": "complete", "subscription": "sub_1", "customer": "cus_123"})


def webhook(client, evenement, secret="whsec_fake"):
    payload = json.dumps(evenement)
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.{payload}".encode(), hashlib.sha256).hexdigest()
    return client.post("/billing/stripe/webhook", content=payload,
                       headers={"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"})


def test_stripe_checkout_et_activation(client, db, make_user, faux_stripe, monkeypatch):
    u, h = make_user()
    r = client.post("/billing/stripe/checkout", json={"devise": "usd"}, headers=h)
    ligne = faux_stripe["session"]["line_items"][0]["price_data"]
    assert r.status_code == 200 and ligne["currency"] == "usd" and ligne["unit_amount"] == 899
    session_de(u, monkeypatch)
    r = client.post("/billing/stripe/confirm", json={"session_id": "cs_test_1"}, headers=h).json()
    assert r["plan"] == "pro" and utilisateur(db, u).stripe_subscription_id == "sub_1"


def test_stripe_session_d_un_autre_utilisateur(client, make_user, faux_stripe, monkeypatch):
    u, h = make_user()
    session_de(u, monkeypatch, autre=True)
    assert client.post("/billing/stripe/confirm", json={"session_id": "cs_test_x"}, headers=h).status_code == 404


def test_stripe_double_abonnement_bloque(client, make_user, faux_stripe):
    _, h = make_user(stripe_customer_id="cus_dup")
    faux_stripe["subs_existants"] = [{"id": "sub_old", "status": "active"}]
    r = client.post("/billing/stripe/checkout", json={"devise": "eur"}, headers=h)
    assert r.status_code == 409 and code(r) == "already_subscribed"
    # Un 3D Secure abandonne ("incomplete") ne bloque pas
    faux_stripe["subs_existants"] = [{"id": "sub_old", "status": "incomplete"}]
    assert client.post("/billing/stripe/checkout", json={"devise": "eur"}, headers=h).status_code == 200


def test_stripe_webhook_signature(client, faux_stripe):
    evt = {"id": "evt_1", "type": "customer.subscription.updated", "data": {"object": {"customer": "cus_x"}}}
    assert webhook(client, evt, secret="mauvais").status_code == 400


def test_stripe_resiliation_garde_le_pro_jusqu_a_la_fin(client, db, make_user, faux_stripe, monkeypatch):
    u, h = make_user()
    client.post("/billing/stripe/checkout", json={"devise": "eur"}, headers=h)
    session_de(u, monkeypatch)
    client.post("/billing/stripe/confirm", json={"session_id": "cs_test_1"}, headers=h)
    evt = {"id": "evt_2", "type": "customer.subscription.deleted", "data": {"object": {
        "id": "sub_1", "customer": faux_stripe["cus"], "status": "canceled", "items": {"data": [{"current_period_end": FIN}]}}}}
    assert webhook(client, evt).status_code == 200
    x = utilisateur(db, u)
    assert x.stripe_subscription_id is None and billing.est_pro(x)


@pytest.mark.parametrize("evenement", [
    {"type": "charge.refunded", "data": {"object": {"id": "ch_1", "customer": "CUS", "refunded": True}}},
    {"type": "charge.dispute.created", "data": {"object": {"id": "dp_1", "charge": "ch_1"}}},
])
def test_stripe_remboursement_ou_contestation_retire_le_pro(client, db, make_user, faux_stripe, monkeypatch, evenement):
    u, h = make_user()
    client.post("/billing/stripe/checkout", json={"devise": "eur"}, headers=h)
    session_de(u, monkeypatch)
    client.post("/billing/stripe/confirm", json={"session_id": "cs_test_1"}, headers=h)
    assert billing.est_pro(utilisateur(db, u))
    objet = {k: (faux_stripe["cus"] if v == "CUS" else v) for k, v in evenement["data"]["object"].items()}
    assert webhook(client, {"id": "evt_3", "type": evenement["type"], "data": {"object": objet}}).status_code == 200
    assert not billing.est_pro(utilisateur(db, u))


def test_remboursement_partiel_ne_retire_pas_le_pro(client, db, make_user, faux_stripe, monkeypatch):
    u, h = make_user()
    client.post("/billing/stripe/checkout", json={"devise": "eur"}, headers=h)
    session_de(u, monkeypatch)
    client.post("/billing/stripe/confirm", json={"session_id": "cs_test_1"}, headers=h)
    evt = {"id": "evt_4", "type": "charge.refunded", "data": {"object": {"id": "ch_2", "customer": faux_stripe["cus"], "refunded": False}}}
    assert webhook(client, evt).status_code == 200
    assert billing.est_pro(utilisateur(db, u))
