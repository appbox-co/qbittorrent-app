-- Publish the verified -6 candidate and retain -5 for rollback.
BEGIN;
DO $publish$
DECLARE
    affected integer;
BEGIN
    PERFORM 1 FROM apps WHERE id=211 AND version='5.2.4_2.0.15.0-5'
        AND tag='5.2.4_2.0.15.0-5' AND "Image"='qbittorrent'
        AND registry='repo.cylo.net' FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'App default changed'; END IF;
    PERFORM 1 FROM app_versions WHERE app_id=211 AND version='5.2.4_2.0.15.0-6'
        AND tag='5.2.4_2.0.15.0-6' AND is_default=0 AND enabled=1 AND admin_only=1
        AND installed_image_digest='repo.cylo.net/qbittorrent@sha256:7694de6a270893380b81a682a9bbc7b27744d19326c9370681adc7f4e6bdd865' AND length(changes)>0 FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Release candidate changed'; END IF;
    PERFORM 1 FROM customfields WHERE type='app' AND relid=211
        AND version='5.2.4_2.0.15.0-6' AND fname='ENABLE_VUETORRENT'
        AND fieldtype='selector' AND display_name='Web interface'
        AND options::jsonb='{"menuItems":{"0":"qBittorrent","1":"VueTorrent","qui":"qui"}}'::jsonb;
    IF NOT FOUND THEN RAISE EXCEPTION 'GUI selector changed'; END IF;
    UPDATE app_versions SET is_default=0,updated_at=now()
        WHERE id=1467 AND app_id=211 AND version='5.2.4_2.0.15.0-5'
            AND enabled=1 AND is_default=1;
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>1 THEN RAISE EXCEPTION 'Expected one previous default'; END IF;
    UPDATE app_versions SET is_default=1,admin_only=0,updated_at=now()
        WHERE app_id=211 AND version='5.2.4_2.0.15.0-6'
            AND is_default=0 AND enabled=1 AND admin_only=1
            AND installed_image_digest='repo.cylo.net/qbittorrent@sha256:7694de6a270893380b81a682a9bbc7b27744d19326c9370681adc7f4e6bdd865';
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>1 THEN RAISE EXCEPTION 'Expected one new default'; END IF;
    UPDATE apps SET version='5.2.4_2.0.15.0-6',tag='5.2.4_2.0.15.0-6',
        registry='repo.cylo.net',updated_at=now()
        WHERE id=211 AND version='5.2.4_2.0.15.0-5' AND tag='5.2.4_2.0.15.0-5'
            AND "Image"='qbittorrent' AND registry='repo.cylo.net';
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>1 THEN RAISE EXCEPTION 'Expected one app default update'; END IF;
    IF (SELECT count(*) FROM app_versions WHERE app_id=211 AND is_default=1)<>1
    THEN RAISE EXCEPTION 'Default version count mismatch'; END IF;
END;
$publish$;
COMMIT;
