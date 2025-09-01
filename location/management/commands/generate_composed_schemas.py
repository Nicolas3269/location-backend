"""
Génère des schemas Zod composables depuis les serializers DRF composés.
Suit le principe de composition pour une meilleure maintenabilité.
"""

from django.core.management.base import BaseCommand
from rest_framework import serializers
from datetime import datetime
import inspect


class Command(BaseCommand):
    help = "Génère des schemas Zod composables depuis les serializers DRF"
    
    def handle(self, *args, **options):
        # Importer les serializers composés
        from location.serializers_composed import (
            # Atomiques
            AdresseSerializer,
            CaracteristiquesBienSerializer,
            PerformanceEnergetiqueSerializer,
            EquipementsSerializer,
            SystemeEnergieSerializer,
            EnergieSerializer,
            RegimeJuridiqueSerializer,
            ZoneReglementaireSerializer,
            PersonneSerializer,
            SocieteSerializer,
            BailleurInfoSerializer,
            LocataireInfoSerializer,
            ModalitesFinancieresSerializer,
            ModalitesZoneTendueSerializer,
            DatesLocationSerializer,
            # Composés
            BienQuittanceSerializer,
            BienEtatLieuxSerializer,
            BienBailSerializer,
        )
        
        # Importer les serializers par pays
        from location.serializers import (
            FranceBailSerializer,
            FranceQuittanceSerializer,
            FranceEtatLieuxSerializer,
            BelgiumBailSerializer,
            BelgiumQuittanceSerializer,
            BelgiumEtatLieuxSerializer,
        )
        
        serializers_atomiques = [
            AdresseSerializer,
            CaracteristiquesBienSerializer,
            PerformanceEnergetiqueSerializer,
            EquipementsSerializer,
            SystemeEnergieSerializer,
            EnergieSerializer,
            RegimeJuridiqueSerializer,
            ZoneReglementaireSerializer,
            PersonneSerializer,
            SocieteSerializer,
            BailleurInfoSerializer,
            LocataireInfoSerializer,
            ModalitesFinancieresSerializer,
            ModalitesZoneTendueSerializer,
            DatesLocationSerializer,
        ]
        
        serializers_composes = [
            BienQuittanceSerializer,
            BienEtatLieuxSerializer,
            BienBailSerializer,
        ]
        
        # Serializers par pays
        serializers_pays = [
            FranceBailSerializer,
            FranceQuittanceSerializer,
            FranceEtatLieuxSerializer,
            BelgiumBailSerializer,
            BelgiumQuittanceSerializer,
            BelgiumEtatLieuxSerializer,
        ]
        
        # Générer les schemas Zod composables
        zod_content = self.generate_composed_zod_schemas(
            serializers_atomiques, 
            serializers_composes,
            serializers_pays
        )
        
        output_path = "/home/havardn/location/frontend/src/types/generated/schemas-composed.zod.ts"
        with open(output_path, "w") as f:
            f.write(zod_content)
        
        # Générer un exemple d'utilisation
        example_content = self.generate_usage_examples()
        example_path = "/home/havardn/location/frontend/src/types/generated/COMPOSED_EXAMPLES.md"
        with open(example_path, "w") as f:
            f.write(example_content)
        
        self.stdout.write(
            self.style.SUCCESS(f"✅ Schemas Zod composables générés dans {output_path}")
        )
        self.stdout.write(
            self.style.SUCCESS(f"✅ Exemples d'utilisation générés dans {example_path}")
        )
    
    def generate_composed_zod_schemas(self, atomiques, composes, pays=None):
        """Génère les schemas Zod en respectant la composition."""
        
        lines = [
            "// Auto-generated Composed Zod Schemas from DRF",
            f"// Generated at: {datetime.now().isoformat()}",
            "// Architecture : Composition de schemas atomiques réutilisables",
            "/* eslint-disable @typescript-eslint/no-explicit-any */",
            "",
            "import { z } from 'zod';",
            "",
            "// ============================================",
            "// SCHEMAS ATOMIQUES (Building blocks)",
            "// ============================================",
            "",
        ]
        
        # Générer les schemas atomiques
        for serializer_class in atomiques:
            schema_name = self.get_schema_name(serializer_class)
            # Formatter le docstring pour JavaScript
            doc = serializer_class.__doc__ or f'Schema {schema_name}'
            # Nettoyer et formater le docstring
            doc_clean = ' '.join(line.strip() for line in doc.split('\n') if line.strip())
            lines.append(f"// {doc_clean}")
            lines.append(f"export const {schema_name} = z.object({{")
            
            instance = serializer_class()
            for field_name, field in instance.fields.items():
                zod_type = self.field_to_zod(field, field_name)
                optional = not field.required
                
                comment = ""
                if hasattr(field, 'help_text') and field.help_text:
                    comment = f"  // {field.help_text}"
                
                if optional:
                    lines.append(f"  {field_name}: {zod_type}.optional(),{comment}")
                else:
                    lines.append(f"  {field_name}: {zod_type},{comment}")
            
            lines.append("});")
            lines.append("")
        
        lines.extend([
            "// ============================================",
            "// SCHEMAS COMPOSÉS (Compositions)",
            "// ============================================",
            "",
        ])
        
        # Générer les schemas composés
        for serializer_class in composes:
            schema_name = self.get_schema_name(serializer_class)
            # Formatter le docstring pour JavaScript
            doc = serializer_class.__doc__ or f'Schema {schema_name}'
            # Nettoyer et formater le docstring
            doc_clean = ' '.join(line.strip() for line in doc.split('\n') if line.strip())
            lines.append(f"// {doc_clean}")
            
            # Vérifier si c'est une vraie composition
            if hasattr(serializer_class, 'Meta') and hasattr(serializer_class.Meta, 'is_composite') and serializer_class.Meta.is_composite:
                lines.append(f"export const {schema_name} = z.object({{")
                
                instance = serializer_class()
                for field_name, field in instance.fields.items():
                    # Si c'est un nested serializer, on utilise son schema
                    if isinstance(field, serializers.Serializer):
                        nested_schema = self.get_schema_name(field.__class__)
                        optional = not field.required
                        
                        if optional:
                            lines.append(f"  {field_name}: {nested_schema}.optional(),")
                        else:
                            lines.append(f"  {field_name}: {nested_schema},")
                    elif isinstance(field, serializers.ListField) and isinstance(field.child, serializers.Serializer):
                        # Liste de serializers
                        child_schema = self.get_schema_name(field.child.__class__)
                        lines.append(f"  {field_name}: z.array({child_schema}),")
                    else:
                        # Champ normal
                        zod_type = self.field_to_zod(field, field_name)
                        optional = not field.required
                        
                        if optional:
                            lines.append(f"  {field_name}: {zod_type}.optional(),")
                        else:
                            lines.append(f"  {field_name}: {zod_type},")
                
                lines.append("});")
            else:
                # Pas une composition, générer normalement
                lines.append(f"export const {schema_name} = z.object({{")
                instance = serializer_class()
                for field_name, field in instance.fields.items():
                    zod_type = self.field_to_zod(field, field_name)
                    optional = not field.required
                    
                    if optional:
                        lines.append(f"  {field_name}: {zod_type}.optional(),")
                    else:
                        lines.append(f"  {field_name}: {zod_type},")
                lines.append("});")
            
            lines.append("")
        
        # Générer les schemas par pays si fournis
        if pays:
            lines.extend([
                "",
                "// ============================================",
                "// SCHEMAS PAR PAYS (Règles métier spécifiques)",
                "// ============================================",
                "",
            ])
            
            for serializer_class in pays:
                schema_name = self.get_schema_name(serializer_class)
                doc = serializer_class.__doc__ or f'Schema {schema_name}'
                doc_clean = ' '.join(line.strip() for line in doc.split('\n') if line.strip())
                lines.append(f"// {doc_clean}")
                lines.append(f"export const {schema_name} = z.object({{")
                
                instance = serializer_class()
                for field_name, field in instance.fields.items():
                    # Si c'est un champ composé (comme BienBailSerializer)
                    if isinstance(field, serializers.Serializer):
                        nested_schema = self.get_schema_name(field.__class__)
                        optional = not field.required
                        if optional:
                            lines.append(f"  {field_name}: {nested_schema}.optional(),")
                        else:
                            lines.append(f"  {field_name}: {nested_schema},")
                    elif isinstance(field, serializers.ListField) and isinstance(field.child, serializers.Serializer):
                        child_schema = self.get_schema_name(field.child.__class__)
                        lines.append(f"  {field_name}: z.array({child_schema}),")
                    else:
                        zod_type = self.field_to_zod(field, field_name)
                        optional = not field.required
                        if optional:
                            lines.append(f"  {field_name}: {zod_type}.optional(),")
                        else:
                            lines.append(f"  {field_name}: {zod_type},")
                
                lines.append("});")
                lines.append("")
        
        # Ajouter les types TypeScript
        lines.extend([
            "// ============================================",
            "// TYPES TYPESCRIPT INFÉRÉS",
            "// ============================================",
            "",
        ])
        
        all_serializers = atomiques + composes
        if pays:
            all_serializers += pays
            
        for serializer_class in all_serializers:
            schema_name = self.get_schema_name(serializer_class)
            type_name = schema_name.replace('Schema', '')
            lines.append(f"export type {type_name} = z.infer<typeof {schema_name}>;")
        
        lines.extend([
            "",
            "// ============================================",
            "// HELPERS DE COMPOSITION",
            "// ============================================",
            "",
            "/**",
            " * Merge plusieurs schemas en un seul (flat)",
            " */",
            "export function mergeSchemas<T extends z.ZodRawShape[]>(...schemas: T) {",
            "  const merged: any = {};",
            "  schemas.forEach(schema => {",
            "    Object.entries(schema).forEach(([key, value]) => {",
            "      merged[key] = value;",
            "    });",
            "  });",
            "  return z.object(merged);",
            "}",
            "",
            "/**",
            " * Schema pour un formulaire de bail complet (flat)",
            " * Utilise mergeSchemas pour aplatir la structure",
            " */",
            "export const BailFormFlatSchema = mergeSchemas(",
            "  AdresseSchema.shape,",
            "  CaracteristiquesBienSchema.shape,",
            "  PerformanceEnergetiqueSchema.shape,",
            "  EquipementsSchema.shape,",
            "  EnergieSchema.shape,",
            "  RegimeJuridiqueSchema.shape,",
            "  ZoneReglementaireSchema.shape,",
            "  // Note: Pour bailleur et locataires, on les garde séparés",
            ").extend({",
            "  bailleur: BailleurInfoSchema,",
            "  locataires: z.array(LocataireInfoSchema),",
            "  modalites_financieres: ModalitesFinancieresSchema,",
            "  modalites_zone_tendue: ModalitesZoneTendueSchema.optional(),",
            "  dates: DatesLocationSchema,",
            "  solidaires: z.boolean().default(false),",
            "});",
            "",
            "// ============================================",
            "// TRANSFORMERS POUR CONVERSION",
            "// ============================================",
            "",
            "/**",
            " * Convertit une structure composée en structure plate",
            " */",
            "export function flattenComposed(data: FranceBail | FranceQuittance | FranceEtatLieux): any {",
            "  const flattened: any = {",
            "    source: data.source,",
            "    solidaires: data.solidaires,",
            "  };",
            "  ",
            "  // Aplatir bien",
            "  if (data.bien) {",
            "    const bien: any = data.bien;",
            "    Object.assign(flattened, ",
            "      bien.localisation || {},",
            "      bien.caracteristiques || {},",
            "      bien.performance_energetique || {},",
            "      bien.equipements || {},",
            "      bien.energie || {},",
            "      bien.regime || {},",
            "      bien.zone_reglementaire || {}",
            "    );",
            "  }",
            "  ",
            "  // Garder les autres comme objets",
            "  flattened.bailleur = data.bailleur;",
            "  flattened.locataires = data.locataires;",
            "  if ('modalites_financieres' in data) flattened.modalites_financieres = data.modalites_financieres;",
            "  if ('modalites_zone_tendue' in data) flattened.modalites_zone_tendue = data.modalites_zone_tendue;",
            "  if ('dates' in data) flattened.dates = data.dates;",
            "  ",
            "  return flattened;",
            "}",
            "",
            "/**",
            " * Convertit une structure plate en structure composée",
            " */",
            "export function composeFromFlat(data: any): FranceBail {",
            "  return {",
            "    source: data.source || 'manual',",
            "    bien: {",
            "      localisation: {",
            "        adresse: data.adresse,",
            "        latitude: data.latitude,",
            "        longitude: data.longitude,",
            "        area_id: data.area_id,",
            "      },",
            "      caracteristiques: {",
            "        superficie: data.superficie,",
            "        type_bien: data.type_bien,",
            "        etage: data.etage,",
            "        porte: data.porte,",
            "        dernier_etage: data.dernier_etage,",
            "        meuble: data.meuble,",
            "        pieces_info: data.pieces_info,",
            "      },",
            "      performance_energetique: {",
            "        classe_dpe: data.classe_dpe,",
            "        depenses_energetiques: data.depenses_energetiques,",
            "      },",
            "      equipements: {",
            "        annexes_privatives: data.annexes_privatives,",
            "        annexes_collectives: data.annexes_collectives,",
            "        information: data.information,",
            "      },",
            "      energie: {",
            "        chauffage: data.chauffage,",
            "        eau_chaude: data.eau_chaude,",
            "      },",
            "      regime: {",
            "        regime_juridique: data.regime_juridique,",
            "        identifiant_fiscal: data.identifiant_fiscal,",
            "        periode_construction: data.periode_construction,",
            "      },",
            "      zone_reglementaire: {",
            "        zone_tendue: data.zone_tendue,",
            "        permis_de_louer: data.permis_de_louer,",
            "      },",
            "    },",
            "    bailleur: data.bailleur,",
            "    locataires: data.locataires,",
            "    modalites_financieres: data.modalites_financieres,",
            "    modalites_zone_tendue: data.modalites_zone_tendue,",
            "    dates: data.dates,",
            "    solidaires: data.solidaires,",
            "  };",
            "}",
            "",
        ])
        
        return "\n".join(lines)
    
    def get_schema_name(self, serializer_class):
        """Génère le nom du schema Zod depuis le nom du serializer."""
        name = serializer_class.__name__
        # Enlever 'Serializer' et ajouter 'Schema'
        if name.endswith('Serializer'):
            name = name[:-10]
        return name + 'Schema'
    
    def field_to_zod(self, field, field_name=None):
        """Convertit un champ DRF en validation Zod."""
        
        # CharField
        if isinstance(field, serializers.CharField):
            validators = []
            if hasattr(field, 'max_length') and field.max_length:
                validators.append(f".max({field.max_length})")
            if field.required and not getattr(field, 'allow_blank', False):
                validators.append(".min(1, 'Requis')")
            
            # Validations spécifiques par nom
            if field_name == 'siret':
                return "z.string().length(14, 'SIRET: 14 chiffres').regex(/^\\d{14}$/)"
            elif field_name == 'email':
                return "z.string().email('Email invalide')"
            elif 'telephone' in (field_name or '').lower() or 'phone' in (field_name or '').lower():
                return "z.string().regex(/^[+\\d\\s()-]*$/)"
            
            return "z.string()" + ''.join(validators)
        
        # EmailField
        if isinstance(field, serializers.EmailField):
            return "z.string().email('Email invalide')"
        
        # DecimalField
        if isinstance(field, serializers.DecimalField):
            validators = []
            if hasattr(field, 'max_digits') and hasattr(field, 'decimal_places'):
                validators.append(f".positive()")
                if hasattr(field, 'max_value') and field.max_value is not None:
                    validators.append(f".max({field.max_value})")
            return "z.number()" + ''.join(validators)
        
        # IntegerField
        if isinstance(field, serializers.IntegerField):
            validators = []
            if hasattr(field, 'min_value') and field.min_value is not None:
                validators.append(f".min({field.min_value})")
            if hasattr(field, 'max_value') and field.max_value is not None:
                validators.append(f".max({field.max_value})")
            return "z.number().int()" + ''.join(validators)
        
        # BooleanField
        if isinstance(field, serializers.BooleanField):
            return "z.boolean()"
        
        # DateField
        if isinstance(field, serializers.DateField):
            return "z.string().regex(/^\\d{4}-\\d{2}-\\d{2}$/, 'Format: YYYY-MM-DD')"
        
        # ChoiceField
        if isinstance(field, serializers.ChoiceField):
            if hasattr(field, 'choices'):
                choices = field.choices
                if isinstance(choices, list) and len(choices) > 0:
                    # Si c'est une liste de tuples (value, label)
                    if isinstance(choices[0], tuple):
                        values = [f"'{c[0]}'" for c in choices]
                    else:
                        values = [f"'{c}'" for c in choices]
                    return f"z.enum([{', '.join(values)}])"
                elif isinstance(choices, dict):
                    values = [f"'{k}'" for k in choices.keys()]
                    return f"z.enum([{', '.join(values)}])"
        
        # ListField
        if isinstance(field, serializers.ListField):
            child_type = "z.any()"
            if field.child:
                if isinstance(field.child, serializers.Serializer):
                    child_type = self.get_schema_name(field.child.__class__)
                else:
                    child_type = self.field_to_zod(field.child)
            
            validators = []
            if hasattr(field, 'min_length') and field.min_length is not None:
                validators.append(f".min({field.min_length})")
            if hasattr(field, 'max_length') and field.max_length is not None:
                validators.append(f".max({field.max_length})")
            
            return f"z.array({child_type})" + ''.join(validators)
        
        # DictField
        if isinstance(field, serializers.DictField):
            return "z.record(z.string(), z.any())"
        
        # HiddenField
        if isinstance(field, serializers.HiddenField):
            default = field.default
            if isinstance(default, str):
                return f"z.literal('{default}')"
            return f"z.literal({default})"
        
        # UUIDField
        if isinstance(field, serializers.UUIDField):
            return "z.string().uuid()"
        
        # Nested Serializer
        if isinstance(field, serializers.Serializer):
            return self.get_schema_name(field.__class__)
        
        return "z.any()"
    
    def generate_usage_examples(self):
        """Génère des exemples d'utilisation."""
        
        return """# 📚 Exemples d'utilisation des Schemas Composés

## 🏗️ Architecture de Composition

Les schemas sont organisés en deux niveaux :

### 1. **Schemas Atomiques** (Building blocks)
- `AdresseSchema` : Adresse avec géolocalisation
- `CaracteristiquesBienSchema` : Caractéristiques physiques
- `PersonneBaseSchema` : Informations de base d'une personne
- etc.

### 2. **Schemas Composés** (Assemblages)
- `BienCompletSchema` : Composition de tous les aspects d'un bien
- `CreateLocationComposedSchema` : Composition complète pour créer une location

## 💡 Exemples d'utilisation

### Exemple 1 : Valider juste une adresse

```typescript
import { AdresseSchema } from '@/types/generated/schemas-composed.zod'

const adresse = {
  adresse: "123 rue de la Paix, Paris",
  latitude: 48.8566,
  longitude: 2.3522
}

const result = AdresseSchema.safeParse(adresse)
if (result.success) {
  console.log("Adresse valide !")
}
```

### Exemple 2 : Composer un bien complet

```typescript
import { BienCompletSchema } from '@/types/generated/schemas-composed.zod'

const bien = {
  localisation: {
    adresse: "123 rue de la Paix, Paris",
    latitude: 48.8566,
    longitude: 2.3522
  },
  caracteristiques: {
    superficie: 65,
    type_bien: 'appartement',
    etage: '3',
    pieces_info: {chambres: 2, sallesDeBain: 1}
  },
  performance_energetique: {
    classe_dpe: 'C',
    depenses_energetiques: '1200'
  },
  // ... autres propriétés
}

const result = BienCompletSchema.safeParse(bien)
```

### Exemple 3 : Utiliser la composition plate (pour les formulaires)

```typescript
import { 
  BailFormFlatSchema, 
  flattenComposed, 
  composeFromFlat 
} from '@/types/generated/schemas-composed.zod'

// Pour un formulaire, on préfère une structure plate
const formData = {
  // Tout au même niveau (flat)
  adresse: "123 rue de la Paix",
  superficie: 65,
  type_bien: 'appartement',
  classe_dpe: 'C',
  // ...
}

// Valider avec le schema plat
const validated = BailFormFlatSchema.parse(formData)

// Convertir en structure composée pour l'API
const composed = composeFromFlat(validated)

// Envoyer à l'API
await fetch('/api/locations', {
  method: 'POST',
  body: JSON.stringify(composed)
})
```

### Exemple 4 : Réutiliser des schemas atomiques

```typescript
import { 
  PersonneBaseSchema,
  AdresseSchema 
} from '@/types/generated/schemas-composed.zod'

// Créer un nouveau schema en combinant des atomiques
const ContactSchema = PersonneBaseSchema.extend({
  adresse_postale: AdresseSchema,
  preferences_contact: z.object({
    email: z.boolean(),
    telephone: z.boolean(),
    courrier: z.boolean()
  })
})

// Utiliser le nouveau schema
const contact = {
  nom: "Dupont",
  prenom: "Jean",
  email: "jean@example.com",
  adresse_postale: {
    adresse: "123 rue Example",
    // ...
  },
  preferences_contact: {
    email: true,
    telephone: false,
    courrier: true
  }
}

ContactSchema.parse(contact)
```

### Exemple 5 : Validation partielle pour un wizard

```typescript
// Pour un formulaire en plusieurs étapes
import { 
  AdresseSchema,
  CaracteristiquesBienSchema,
  BailleurInfoSchema 
} from '@/types/generated/schemas-composed.zod'

// Étape 1 : Valider seulement l'adresse
function validateStep1(data: any) {
  return AdresseSchema.safeParse(data)
}

// Étape 2 : Valider les caractéristiques
function validateStep2(data: any) {
  return CaracteristiquesBienSchema.safeParse(data)
}

// Étape 3 : Valider le bailleur
function validateStep3(data: any) {
  return BailleurInfoSchema.safeParse(data)
}

// À la fin, valider le tout
function validateComplete(data: any) {
  return CreateLocationComposedSchema.safeParse(data)
}
```

## 🔄 Migration depuis l'ancienne approche

### Avant (schema monolithique)
```typescript
const formSchema = z.object({
  adresse: z.string(),
  superficie: z.number(),
  type_bien: z.string(),
  // ... 50+ champs dans un seul objet
})
```

### Après (schemas composés)
```typescript
const formSchema = z.object({
  localisation: AdresseSchema,
  caracteristiques: CaracteristiquesBienSchema,
  // ... schemas atomiques réutilisables
})
```

## ✨ Avantages de la composition

1. **Réutilisabilité** : Les schemas atomiques peuvent être réutilisés
2. **Maintenabilité** : Chaque schema a une responsabilité unique
3. **Testabilité** : On peut tester chaque schema indépendamment
4. **Évolutivité** : Facile d'ajouter de nouveaux schemas composés
5. **Type-safety** : TypeScript infère les types correctement

## 🎯 Best Practices

1. **Utilisez les schemas atomiques** pour les validations unitaires
2. **Composez les schemas** pour les objets complexes
3. **Utilisez `flattenComposed`** pour les formulaires
4. **Utilisez `composeFromFlat`** pour l'API
5. **Étendez les schemas** avec `.extend()` pour des cas spécifiques
"""