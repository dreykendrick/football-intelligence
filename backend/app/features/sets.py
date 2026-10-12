"""
Feature Set Manager
Initializes, manages, and fingerprint-verifies versioned FeatureSet definitions and compositions in the database.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import FeatureDefinition, FeatureSet, FeatureSetFeature
from app.features.definitions import CORE_FEATURE_DEFINITIONS
from app.features.fingerprint import FeatureSetFingerprintCalculator
from app.features.registry import FEATURE_CATALOG, global_feature_registry


class FeatureSetManager:
    """Manages creation, fingerprinting, and lookup of versioned FeatureSet entities."""

    MVP_A_SET_NAME: str = "mvp_a_feature_set_v1"
    MVP_A_SET_VERSION: str = "1.0.0"

    @classmethod
    def get_or_create_mvp_a_feature_set(cls, db: Session) -> FeatureSet:
        from app.features.manifest import get_mvp_a_feature_set_v1_manifest
        manifest = get_mvp_a_feature_set_v1_manifest()
        return cls.get_or_create_feature_set(
            db=db,
            name=manifest.feature_set_key,
            version=manifest.version,
            description=manifest.scientific_notes,
            feature_keys=manifest.included_feature_keys,
        )

    @classmethod
    def get_or_create_feature_set(
        cls,
        db: Session,
        name: str,
        version: str,
        description: str,
        feature_keys: list[str],
        dataset_key: str = "mvp_a_historical",
        dataset_version: str = "v1",
    ) -> FeatureSet:
        fset = (
            db.query(FeatureSet)
            .filter_by(name=name, version=version)
            .first()
        )
        if not fset:
            fset = FeatureSet(
                name=name,
                version=version,
                description=description[:255] if description else None,
                is_active=True,
            )
            db.add(fset)
            db.flush()

            # Compute and verify fingerprint
            fingerprint = FeatureSetFingerprintCalculator.compute_fingerprint(
                name=name,
                version=version,
                feature_keys=feature_keys,
                dataset_key=dataset_key,
                dataset_version=dataset_version,
            )

            # Register feature definitions & junction records
            for order, fkey in enumerate(sorted(feature_keys), start=1):
                fdef = db.query(FeatureDefinition).filter_by(feature_key=fkey).first()
                calc = FEATURE_CATALOG.get(fkey)
                def_meta = CORE_FEATURE_DEFINITIONS.get(fkey)

                calc_desc = calc.description if calc else fkey
                calc_ver = calc.version if calc else "1.0.0"
                category = def_meta.category if def_meta else "STRENGTH"
                data_type = def_meta.data_type if def_meta else "FLOAT"

                if not fdef:
                    fdef = FeatureDefinition(
                        feature_key=fkey,
                        name=def_meta.name if def_meta else fkey.replace("_", " ").title(),
                        description=def_meta.description if def_meta else calc_desc,
                        data_type=data_type,
                        category=category,
                        version=calc_ver,
                        is_active=True,
                    )
                    db.add(fdef)
                    db.flush()

                junction = FeatureSetFeature(
                    feature_set_id=fset.id,
                    feature_definition_id=fdef.id,
                    display_order=order,
                )
                db.add(junction)

            db.commit()

        return fset
