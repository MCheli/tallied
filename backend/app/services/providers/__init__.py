"""Registry of data providers. Add a provider here and nothing else in the sync path changes."""
from app.services.providers.base import Provider, ProviderError  # noqa: F401
from app.services.providers.simplefin import SimpleFinProvider

PROVIDERS: dict[str, Provider] = {
    SimpleFinProvider.name: SimpleFinProvider(),
}

ALL_PROVIDERS: tuple[str, ...] = tuple(PROVIDERS)


def get_provider(name: str) -> Provider:
    try:
        return PROVIDERS[name]
    except KeyError:
        raise KeyError(f"unknown provider: {name}")
