"""
Baseline Model Implementations Package
Registers baseline statistical prediction models: Class Prior 1X2, Multinomial Logistic Regression 1X2, and Poisson Goals.
"""
from app.models.baselines.attack_defense_poisson import AttackDefensePoissonModel
from app.models.baselines.league_average import LeagueAveragePoissonModel
from app.models.baselines.calibrated_model import CalibratedPredictionModel
from app.models.baselines.class_prior import ClassPrior1X2Model
from app.models.baselines.competition_prior import CompetitionPrior1X2Model
from app.models.baselines.elo_logistic import EloLogistic1X2Model
from app.models.baselines.multinomial_logistic import MultinomialLogistic1X2Model
from app.models.baselines.poisson_goals import PoissonGoalsModel
from app.models.baselines.gradient_boosted_tree import GradientBoosted1X2Model
from app.models.baselines.poisson_features import FeatureGoalRegressorModel
from app.models.baselines.hybrid_model import HybridStructuralFeatureModel
from app.models.registry import global_model_registry

# Auto-register baseline models into global registry
global_model_registry.register(ClassPrior1X2Model)
global_model_registry.register(CompetitionPrior1X2Model)
global_model_registry.register(EloLogistic1X2Model)
global_model_registry.register(MultinomialLogistic1X2Model)
global_model_registry.register(PoissonGoalsModel)
global_model_registry.register(GradientBoosted1X2Model)
global_model_registry.register(FeatureGoalRegressorModel)
global_model_registry.register(HybridStructuralFeatureModel)
global_model_registry.register(AttackDefensePoissonModel)
global_model_registry.register(LeagueAveragePoissonModel)
global_model_registry.register(CalibratedPredictionModel)

__all__ = [
    "ClassPrior1X2Model",
    "CompetitionPrior1X2Model",
    "EloLogistic1X2Model",
    "MultinomialLogistic1X2Model",
    "PoissonGoalsModel",
    "AttackDefensePoissonModel",
    "LeagueAveragePoissonModel",
    "CalibratedPredictionModel",
]

