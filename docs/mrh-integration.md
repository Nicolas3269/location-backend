# Intégration MRH Locataire - Mila

## Vue d'ensemble

Hestia propose une assurance Multirisque Habitation (MRH) aux locataires via le partenaire **Mila**.

**Modèle d'intégration** : API Only (Modèle 2)
- Mila fournit uniquement l'API de tarification
- Hestia génère les documents contractuels
- Hestia encaisse les primes et conserve la commission courtier
- Numérotation des polices : `PO-MRHIND-67XXXXXXX`

---

## Flow Utilisateur

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. CRÉATION BAIL (Bailleur)                                        │
│     └─ Bailleur crée le bail avec infos bien + locataire           │
│     └─ Envoie lien de signature au locataire                       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  2. ACCÈS LOCATAIRE (avant signature)                               │
│     └─ Locataire clique sur le lien                                │
│     └─ Voit récap du bail + proposition MRH                        │
│     └─ Tarif MRH pré-calculé (API Mila)                           │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  3. SOUSCRIPTION MRH (optionnelle mais recommandée)                 │
│     └─ Locataire choisit une formule                               │
│     └─ Paiement via Stripe Checkout                                │
│     └─ Documents MRH générés (CP, CGV, DIPA)                       │
│     └─ Email avec attestation d'assurance                          │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  4. SIGNATURE BAIL                                                  │
│     └─ Locataire signe le bail                                     │
│     └─ Si MRH souscrite : attestation jointe automatiquement       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Architecture Technique

### Structure des fichiers

```
backend/
├── partenaires/
│   └── services/mila/              # Client API Mila (existant)
│       ├── __init__.py
│       ├── auth.py                 # Authentification OAuth2
│       ├── client.py               # MilaMRHClient
│       ├── types.py                # Dataclasses (MilaAddress, etc.)
│       └── adapters.py             # Conversion Bien → Mila format
│
├── mrh/                            # App Django MRH
│   ├── models.py                   # MRHQuotation, MRHPolicy
│   ├── views.py                    # API endpoints
│   ├── serializers.py
│   ├── urls.py
│   ├── admin.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── quotation.py            # Service tarification
│   │   ├── subscription.py         # Service souscription
│   │   ├── documents.py            # Génération PDF
│   │   ├── policy_number.py        # Génération numéro police
│   │   └── stripe_service.py       # Intégration Stripe
│   ├── templates/pdf/mrh/
│   │   ├── base_mrh.html           # Layout commun
│   │   ├── conditions_particulieres.html
│   │   ├── devis.html
│   │   └── attestation.html
│   └── webhooks.py                 # Stripe webhooks

frontend/
├── src/
│   ├── app/signature/[token]/
│   │   └── page.tsx                # Page signature avec offre MRH
│   ├── components/mrh/
│   │   ├── MRHOfferCard.tsx        # Card proposition MRH
│   │   ├── FormulaSelector.tsx     # Sélection formule
│   │   ├── MRHSummary.tsx          # Récapitulatif avant paiement
│   │   └── MRHCheckoutButton.tsx   # Bouton vers Stripe
│   └── lib/api/mrh.ts              # API client MRH
```

---

## Modèles de données

### MRHQuotation

Stocke les devis demandés (cache tarification).

```python
class MRHQuotation(models.Model):
    """Devis MRH demandé via API Mila."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    # Source
    location = models.ForeignKey('location.Location', on_delete=models.CASCADE)

    # Paramètres de tarification
    deductible = models.IntegerField(default=170)  # Franchise: 170 ou 290
    effective_date = models.DateField()

    # Réponse API Mila (JSON des formules)
    formulas_data = models.JSONField()

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()  # Validité du devis (ex: 30 jours)

    class Meta:
        indexes = [
            models.Index(fields=['location', 'created_at']),
        ]
```

### MRHPolicy

Stocke les polices souscrites.

```python
class MRHPolicy(models.Model):
    """Police d'assurance MRH souscrite."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'En attente de paiement'
        ACTIVE = 'ACTIVE', 'Active'
        CANCELLED = 'CANCELLED', 'Résiliée'
        EXPIRED = 'EXPIRED', 'Expirée'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    # Numéro de police: PO-MRHIND-670000001
    policy_number = models.CharField(max_length=25, unique=True, blank=True)

    # Relations
    location = models.ForeignKey('location.Location', on_delete=models.PROTECT)
    subscriber = models.ForeignKey('users.User', on_delete=models.PROTECT)
    quotation = models.ForeignKey(MRHQuotation, on_delete=models.PROTECT)

    # Formule choisie
    formula_label = models.CharField(max_length=100)  # "Essentielle", "Confort", "Premium"
    formula_code = models.CharField(max_length=50)    # Code produit Mila
    pricing_annual = models.DecimalField(max_digits=10, decimal_places=2)
    pricing_monthly = models.DecimalField(max_digits=10, decimal_places=2)
    deductible = models.IntegerField(default=170)

    # Dates
    effective_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # Null = en cours

    # Statut
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # Stripe
    stripe_checkout_session_id = models.CharField(max_length=100, blank=True)
    stripe_payment_intent_id = models.CharField(max_length=100, blank=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True)

    # Documents générés (FileField vers S3/stockage)
    cp_document = models.FileField(upload_to='mrh/cp/', null=True, blank=True)
    cgv_document = models.FileField(upload_to='mrh/cgv/', null=True, blank=True)
    dipa_document = models.FileField(upload_to='mrh/dipa/', null=True, blank=True)
    attestation_document = models.FileField(upload_to='mrh/attestation/', null=True, blank=True)

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Police MRH"
        verbose_name_plural = "Polices MRH"
        indexes = [
            models.Index(fields=['policy_number']),
            models.Index(fields=['subscriber', 'status']),
            models.Index(fields=['location']),
        ]

    def save(self, *args, **kwargs):
        if not self.policy_number:
            self.policy_number = generate_policy_number()
        super().save(*args, **kwargs)
```

### Génération du numéro de police

```python
# mrh/services/policy_number.py

from django.db import transaction
from django.db.models import Max

def generate_policy_number() -> str:
    """
    Génère un numéro de police au format PO-MRHIND-670000001.

    Format: PO-MRHIND-67XXXXXXX
    - PO: Préfixe police
    - MRHIND: Produit MRH Individuel
    - 67: Code courtier Hestia
    - XXXXXXX: 7 chiffres séquentiels
    """
    from mrh.models import MRHPolicy

    PREFIX = "PO-MRHIND-67"

    with transaction.atomic():
        # Récupérer le dernier numéro
        last_policy = MRHPolicy.objects.select_for_update().aggregate(
            max_number=Max('policy_number')
        )

        if last_policy['max_number']:
            # Extraire le numéro séquentiel
            last_seq = int(last_policy['max_number'].replace(PREFIX, ''))
            new_seq = last_seq + 1
        else:
            new_seq = 1

        return f"{PREFIX}{new_seq:07d}"
```

---

## API Endpoints

### Tarification

```
GET /api/mrh/quotation/?location_id={uuid}
```

Retourne les formules disponibles avec prix.

**Réponse:**
```json
{
  "quotation_id": "uuid",
  "location_id": "uuid",
  "effective_date": "2025-02-01",
  "expires_at": "2025-03-01T00:00:00Z",
  "formulas": [
    {
      "code": "MRHIND_ESS",
      "label": "Essentielle",
      "description": "Protection de base",
      "pricing_annual": 89.00,
      "pricing_monthly": 7.42,
      "features": [
        "Responsabilité civile",
        "Dégâts des eaux",
        "Incendie"
      ]
    },
    {
      "code": "MRHIND_CONF",
      "label": "Confort",
      "description": "Protection étendue",
      "pricing_annual": 129.00,
      "pricing_monthly": 10.75,
      "features": [
        "Tout Essentielle +",
        "Vol et vandalisme",
        "Bris de glace"
      ]
    },
    {
      "code": "MRHIND_PREM",
      "label": "Premium",
      "description": "Protection complète",
      "pricing_annual": 169.00,
      "pricing_monthly": 14.08,
      "features": [
        "Tout Confort +",
        "Objets de valeur",
        "Assistance 24/7"
      ]
    }
  ]
}
```

### Souscription

```
POST /api/mrh/subscribe/
```

Crée une police et redirige vers Stripe Checkout.

**Corps:**
```json
{
  "quotation_id": "uuid",
  "formula_code": "MRHIND_CONF",
  "payment_frequency": "annual"  // ou "monthly"
}
```

**Réponse:**
```json
{
  "policy_id": "uuid",
  "policy_number": "PO-MRHIND-670000001",
  "stripe_checkout_url": "https://checkout.stripe.com/..."
}
```

### Webhook Stripe

```
POST /api/mrh/webhooks/stripe/
```

Reçoit les événements Stripe pour activer les polices.

---

## Intégration Stripe (Elements)

On utilise **Stripe Elements** pour intégrer le formulaire de paiement directement dans le site (pas de redirection).

### Configuration

```python
# settings.py
STRIPE_SECRET_KEY = env('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = env('STRIPE_PUBLISHABLE_KEY')
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET')
```

### Flow avec PaymentIntent

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. Frontend: User choisit formule + clique "Payer"                │
│     └─ POST /api/mrh/create-payment-intent/                        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  2. Backend: Crée PaymentIntent + MRHPolicy (PENDING)              │
│     └─ Retourne client_secret au frontend                          │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  3. Frontend: Affiche Stripe Elements (CardElement)                │
│     └─ User entre sa carte                                         │
│     └─ stripe.confirmPayment(client_secret)                        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  4. Webhook: payment_intent.succeeded                              │
│     └─ MRHPolicy.status = ACTIVE                                   │
│     └─ Génère documents                                            │
│     └─ Envoie email                                                │
└─────────────────────────────────────────────────────────────────────┘
```

### Backend: Service Stripe

```python
# mrh/services/stripe_service.py

import stripe
from django.conf import settings
from django.utils import timezone

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_payment_intent(policy: 'MRHPolicy') -> dict:
    """
    Crée un PaymentIntent pour le paiement MRH.

    Returns:
        {
            'client_secret': 'pi_xxx_secret_xxx',
            'payment_intent_id': 'pi_xxx'
        }
    """
    # Montant en centimes
    amount = int(policy.pricing_annual * 100)

    # Créer ou récupérer le customer Stripe
    customer = get_or_create_stripe_customer(policy.subscriber)

    intent = stripe.PaymentIntent.create(
        amount=amount,
        currency='eur',
        customer=customer.id,
        # Méthodes de paiement acceptées
        payment_method_types=['card', 'sepa_debit'],
        metadata={
            'policy_id': str(policy.id),
            'policy_number': policy.policy_number,
            'type': 'mrh_subscription',
        },
        description=f'Assurance MRH - {policy.formula_label} - {policy.policy_number}',
        receipt_email=policy.subscriber.email,
        # Pour SEPA: autoriser les paiements asynchrones
        payment_method_options={
            'sepa_debit': {
                'mandate_options': {
                    'notification_method': 'email',
                }
            }
        },
    )

    # Sauvegarder l'ID
    policy.stripe_payment_intent_id = intent.id
    policy.save(update_fields=['stripe_payment_intent_id'])

    return {
        'client_secret': intent.client_secret,
        'payment_intent_id': intent.id,
    }


def get_or_create_stripe_customer(user: 'User') -> stripe.Customer:
    """Récupère ou crée un customer Stripe pour l'utilisateur."""
    if user.stripe_customer_id:
        return stripe.Customer.retrieve(user.stripe_customer_id)

    customer = stripe.Customer.create(
        email=user.email,
        name=f'{user.first_name} {user.last_name}',
        metadata={'user_id': str(user.id)},
    )

    user.stripe_customer_id = customer.id
    user.save(update_fields=['stripe_customer_id'])

    return customer


def handle_payment_succeeded(event: dict) -> None:
    """Traite l'événement payment_intent.succeeded."""
    from mrh.models import MRHPolicy
    from mrh.services.documents import generate_all_documents
    from mrh.services.subscription import send_policy_documents_email

    payment_intent = event['data']['object']
    policy_id = payment_intent['metadata'].get('policy_id')

    if not policy_id:
        return  # Pas un paiement MRH

    policy = MRHPolicy.objects.get(id=policy_id)

    # Activer la police
    policy.status = MRHPolicy.Status.ACTIVE
    policy.activated_at = timezone.now()
    policy.save()

    # Générer les documents
    generate_all_documents(policy)

    # Envoyer par email
    send_policy_documents_email(policy)
```

### Backend: API Endpoint

```python
# mrh/views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .services.stripe_service import create_payment_intent
from .models import MRHPolicy, MRHQuotation


@api_view(['POST'])
@permission_classes([AllowAny])  # Le locataire n'est pas forcément connecté
def create_mrh_payment_intent(request):
    """
    Crée un PaymentIntent pour la souscription MRH.

    Body:
    {
        "quotation_id": "uuid",
        "formula_code": "MRHIND_CONF",
        "subscriber_email": "locataire@email.com"
    }
    """
    quotation = MRHQuotation.objects.get(id=request.data['quotation_id'])
    formula_code = request.data['formula_code']

    # Trouver la formule dans le devis
    formula = next(
        (f for f in quotation.formulas_data if f['code'] == formula_code),
        None
    )
    if not formula:
        return Response({'error': 'Formule non trouvée'}, status=400)

    # Créer la police (PENDING)
    policy = MRHPolicy.objects.create(
        location=quotation.location,
        subscriber=get_or_create_user(request.data['subscriber_email']),
        quotation=quotation,
        formula_label=formula['label'],
        formula_code=formula_code,
        pricing_annual=formula['pricing_annual'],
        pricing_monthly=formula['pricing_monthly'],
        deductible=quotation.deductible,
        effective_date=quotation.effective_date,
        status=MRHPolicy.Status.PENDING,
    )

    # Créer le PaymentIntent
    payment_data = create_payment_intent(policy)

    return Response({
        'policy_id': str(policy.id),
        'policy_number': policy.policy_number,
        'client_secret': payment_data['client_secret'],
        'amount': float(policy.pricing_annual),
        'publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
    })
```

### Backend: Webhook Handler

```python
# mrh/webhooks.py

import stripe
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
from .services.stripe_service import handle_payment_succeeded

@csrf_exempt
@require_POST
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    # Traiter les événements
    if event['type'] == 'payment_intent.succeeded':
        handle_payment_succeeded(event)
    elif event['type'] == 'payment_intent.payment_failed':
        handle_payment_failed(event)

    return HttpResponse(status=200)
```

### Frontend: Installation

```bash
cd frontend
yarn add @stripe/stripe-js @stripe/react-stripe-js
```

### Frontend: Provider Stripe

```tsx
// app/providers.tsx (ou layout)

import { Elements } from '@stripe/react-stripe-js'
import { loadStripe } from '@stripe/stripe-js'

const stripePromise = loadStripe(process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY!)

export function StripeProvider({ children }: { children: React.ReactNode }) {
  return (
    <Elements stripe={stripePromise}>
      {children}
    </Elements>
  )
}
```

### Frontend: Composant de paiement

```tsx
// components/mrh/MRHPaymentForm.tsx

'use client'

import { useState } from 'react'
import {
  PaymentElement,
  useStripe,
  useElements,
} from '@stripe/react-stripe-js'
import { Button } from '@/components/ui/button'
import { Loader2, Shield, CheckCircle } from 'lucide-react'

interface MRHPaymentFormProps {
  clientSecret: string
  policyNumber: string
  amount: number
  onSuccess: () => void
}

export function MRHPaymentForm({
  clientSecret,
  policyNumber,
  amount,
  onSuccess,
}: MRHPaymentFormProps) {
  const stripe = useStripe()
  const elements = useElements()
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!stripe || !elements) return

    setIsProcessing(true)
    setError(null)

    const { error: submitError } = await stripe.confirmPayment({
      elements,
      confirmParams: {
        return_url: `${window.location.origin}/mrh/success?policy=${policyNumber}`,
      },
      redirect: 'if_required',
    })

    if (submitError) {
      setError(submitError.message || 'Une erreur est survenue')
      setIsProcessing(false)
    } else {
      // Paiement réussi sans redirection
      onSuccess()
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="bg-muted/50 rounded-lg p-4 flex items-center gap-3">
        <Shield className="h-5 w-5 text-primary" />
        <div>
          <p className="font-medium">Paiement sécurisé</p>
          <p className="text-sm text-muted-foreground">
            Vos données sont protégées par Stripe
          </p>
        </div>
      </div>

      <PaymentElement
        options={{
          layout: 'tabs',
        }}
      />

      {error && (
        <div className="bg-destructive/10 text-destructive rounded-lg p-3 text-sm">
          {error}
        </div>
      )}

      <Button
        type="submit"
        disabled={!stripe || isProcessing}
        className="w-full"
        size="lg"
      >
        {isProcessing ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Paiement en cours...
          </>
        ) : (
          <>
            Payer {amount.toFixed(2)} €
          </>
        )}
      </Button>
    </form>
  )
}
```

### Frontend: Page souscription MRH

```tsx
// components/mrh/MRHSubscription.tsx

'use client'

import { useState } from 'react'
import { Elements } from '@stripe/react-stripe-js'
import { loadStripe } from '@stripe/stripe-js'
import { MRHPaymentForm } from './MRHPaymentForm'
import { FormulaSelector } from './FormulaSelector'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

const stripePromise = loadStripe(process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY!)

interface MRHSubscriptionProps {
  quotation: MRHQuotation
  subscriberEmail: string
}

export function MRHSubscription({ quotation, subscriberEmail }: MRHSubscriptionProps) {
  const [selectedFormula, setSelectedFormula] = useState<string | null>(null)
  const [paymentData, setPaymentData] = useState<{
    clientSecret: string
    policyNumber: string
    amount: number
  } | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)

  const handleProceedToPayment = async () => {
    if (!selectedFormula) return

    setIsLoading(true)

    const response = await fetch('/api/mrh/create-payment-intent/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        quotation_id: quotation.id,
        formula_code: selectedFormula,
        subscriber_email: subscriberEmail,
      }),
    })

    const data = await response.json()
    setPaymentData({
      clientSecret: data.client_secret,
      policyNumber: data.policy_number,
      amount: data.amount,
    })
    setIsLoading(false)
  }

  if (isSuccess) {
    return (
      <Card className="border-success">
        <CardContent className="pt-6 text-center">
          <CheckCircle className="h-12 w-12 text-success mx-auto mb-4" />
          <h3 className="text-xl font-semibold mb-2">Souscription réussie !</h3>
          <p className="text-muted-foreground">
            Votre attestation d'assurance vous sera envoyée par email.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Assurance Habitation</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {!paymentData ? (
          <>
            <FormulaSelector
              formulas={quotation.formulas}
              selected={selectedFormula}
              onSelect={setSelectedFormula}
            />

            <Button
              onClick={handleProceedToPayment}
              disabled={!selectedFormula || isLoading}
              className="w-full"
            >
              {isLoading ? 'Chargement...' : 'Continuer vers le paiement'}
            </Button>
          </>
        ) : (
          <Elements
            stripe={stripePromise}
            options={{
              clientSecret: paymentData.clientSecret,
              appearance: {
                theme: 'stripe',
                variables: {
                  colorPrimary: '#2680eb',
                  borderRadius: '8px',
                },
              },
            }}
          >
            <MRHPaymentForm
              clientSecret={paymentData.clientSecret}
              policyNumber={paymentData.policyNumber}
              amount={paymentData.amount}
              onSuccess={() => setIsSuccess(true)}
            />
          </Elements>
        )}
      </CardContent>
    </Card>
  )
}
```

---

## Génération des Documents

### Service de génération

```python
# mrh/services/documents.py

from django.template.loader import render_to_string
from weasyprint import HTML
from django.core.files.base import ContentFile

def generate_conditions_particulieres(policy: 'MRHPolicy') -> bytes:
    """Génère les Conditions Particulières en PDF."""

    location = policy.location
    bien = location.bien
    subscriber = policy.subscriber

    html = render_to_string('pdf/mrh/conditions_particulieres.html', {
        'policy': policy,
        'location': location,
        'bien': bien,
        'subscriber': subscriber,
        'adresse': bien.adresse,
        'logo_base64_uri': get_logo_pdf_base64_data_uri(),
    })

    return HTML(string=html).write_pdf()


def generate_attestation(policy: 'MRHPolicy') -> bytes:
    """Génère l'attestation d'assurance."""

    html = render_to_string('pdf/mrh/attestation.html', {
        'policy': policy,
        'bien': policy.location.bien,
        'subscriber': policy.subscriber,
        'logo_base64_uri': get_logo_pdf_base64_data_uri(),
    })

    return HTML(string=html).write_pdf()


def generate_all_documents(policy: 'MRHPolicy') -> None:
    """Génère et sauvegarde tous les documents de la police."""

    # Conditions Particulières
    cp_pdf = generate_conditions_particulieres(policy)
    policy.cp_document.save(
        f'cp_{policy.policy_number}.pdf',
        ContentFile(cp_pdf)
    )

    # Attestation
    attestation_pdf = generate_attestation(policy)
    policy.attestation_document.save(
        f'attestation_{policy.policy_number}.pdf',
        ContentFile(attestation_pdf)
    )

    # CGV et DIPA sont des fichiers statiques (copiés depuis templates Mila)
    # Ils peuvent être pré-uploadés ou copiés au moment de la souscription

    policy.save()
```

### Templates HTML

Les templates utilisent le même système que bail/quittance :
- Layout commun avec branding Hestia
- Variables Django pour les données dynamiques
- WeasyPrint pour conversion PDF

---

## Frontend

### Page de signature avec offre MRH

```tsx
// app/signature/[token]/page.tsx

export default async function SignaturePage({ params }: Props) {
  const { token } = params
  const bail = await getBailBySignatureToken(token)

  // Pré-calculer le tarif MRH
  const mrhQuotation = await getMRHQuotation(bail.location_id)

  return (
    <div className="max-w-4xl mx-auto p-6">
      {/* Récapitulatif du bail */}
      <BailSummary bail={bail} />

      {/* Offre MRH */}
      <MRHOfferSection
        quotation={mrhQuotation}
        locationId={bail.location_id}
      />

      {/* Bouton signature */}
      <SignatureSection bail={bail} />
    </div>
  )
}
```

### Composant offre MRH

```tsx
// components/mrh/MRHOfferCard.tsx

interface MRHOfferCardProps {
  quotation: MRHQuotation
  locationId: string
  onSubscribe: (formulaCode: string) => void
}

export function MRHOfferCard({ quotation, onSubscribe }: MRHOfferCardProps) {
  const [selectedFormula, setSelectedFormula] = useState<string | null>(null)

  return (
    <Card className="border-primary/20 bg-gradient-to-br from-primary/5 to-transparent">
      <CardHeader>
        <div className="flex items-center gap-3">
          <Shield className="h-8 w-8 text-primary" />
          <div>
            <CardTitle>Assurance Habitation</CardTitle>
            <CardDescription>
              Protégez votre logement dès maintenant
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <FormulaSelector
          formulas={quotation.formulas}
          selected={selectedFormula}
          onSelect={setSelectedFormula}
        />

        {selectedFormula && (
          <Button
            className="w-full mt-4"
            onClick={() => onSubscribe(selectedFormula)}
          >
            Souscrire maintenant
          </Button>
        )}

        <p className="text-sm text-muted-foreground mt-4 text-center">
          Vous pouvez aussi souscrire plus tard depuis votre espace
        </p>
      </CardContent>
    </Card>
  )
}
```

---

## Variables d'environnement

```bash
# .env

# Mila API
MILA_API_URL=https://api.mila.direct
MILA_CLIENT_ID=xxx
MILA_CLIENT_SECRET=xxx

# Stripe
STRIPE_SECRET_KEY=sk_xxx
STRIPE_PUBLISHABLE_KEY=pk_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx

# URLs de redirection Stripe
MRH_CHECKOUT_SUCCESS_URL=https://app.hestia.fr/mrh/success
MRH_CHECKOUT_CANCEL_URL=https://app.hestia.fr/mrh/cancel
```

---

## Commandes de test

```bash
# Tester la tarification Mila
cd backend
python manage.py test_mila --location-id=xxx

# Tester la génération de documents
python manage.py generate_mrh_documents --policy-id=xxx --dry-run

# Simuler un webhook Stripe (dev)
stripe trigger checkout.session.completed
```

---

## Checklist d'implémentation

- [ ] **Backend**
  - [ ] App Django `mrh`
  - [ ] Modèles `MRHQuotation`, `MRHPolicy`
  - [ ] Migrations
  - [ ] Service tarification (utilise Mila client existant)
  - [ ] Service souscription
  - [ ] Génération numéro police
  - [ ] Templates PDF (CP, attestation)
  - [ ] Service génération documents
  - [ ] Intégration Stripe (Checkout, webhooks)
  - [ ] API endpoints
  - [ ] Tests unitaires

- [ ] **Frontend**
  - [ ] Composants MRH (`MRHOfferCard`, `FormulaSelector`, etc.)
  - [ ] Intégration page signature
  - [ ] Page success/cancel Stripe
  - [ ] Espace locataire : voir ses polices MRH

- [ ] **Configuration**
  - [ ] Variables d'environnement
  - [ ] Produits Stripe (prix annuel/mensuel)
  - [ ] Webhook Stripe configuré

- [ ] **Documentation**
  - [x] Ce document
  - [ ] Guide utilisateur (bailleur/locataire)
