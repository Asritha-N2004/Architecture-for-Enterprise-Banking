from alembic.config import Config
from alembic import command
from sqlalchemy import text
from app.database import make_engine


def test_migration_can_reuse_external_transaction(tmp_path):
    engine = make_engine('sqlite:///' + str(tmp_path / 'external.db').replace('\\', '/'))
    config = Config('backend/alembic.ini')
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0001'
        assert connection.scalar(text('SELECT sequence FROM audit_head WHERE id=1')) == 0
    engine.dispose()
