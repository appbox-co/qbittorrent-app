-- Register 5.2.4_2.0.15.0-6 as a private release candidate by copying the
-- -5 resource contract and its version-specific fields. -6 keeps private
-- torrents seeding whatever the WebUI language: qbtcheck reads qBittorrent's
-- private flag instead of the translated tracker message.
-- -5 stays enabled for the instances that run it.
-- Run only after the exact image passes the release gate and registry verification.
BEGIN;
DO $release$
DECLARE
    baseline app_versions%ROWTYPE;
    candidate app_versions%ROWTYPE;
    new_id integer;
    affected integer;
BEGIN
    PERFORM 1 FROM apps WHERE id=211 AND version='5.2.4_2.0.15.0-5'
        AND tag='5.2.4_2.0.15.0-5' AND app_slots=1 AND "Memory"=100
        AND "MemorySwap"=100 AND "MemoryReservation"=4 AND "CPUs"=0
        AND allow_downgrade=1 AND registry='repo.cylo.net' AND "Image"='qbittorrent' FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'App baseline changed'; END IF;
    SELECT * INTO STRICT baseline FROM app_versions
        WHERE id=1467 AND app_id=211 AND version='5.2.4_2.0.15.0-5'
        AND is_default=1 AND enabled=1 AND admin_only=0
        AND tag='5.2.4_2.0.15.0-5'
        AND installed_image_digest='repo.cylo.net/qbittorrent@sha256:757ae20ba44a289f03c760281d0ec36c831f598b75f8b62dea0f4a19dda7935a' FOR UPDATE;
    IF baseline.memory<>100 OR baseline.memory_swap<>100
        OR baseline.memory_reservation<>4 OR baseline.cpus<>0
        OR baseline.app_slots<>1 OR baseline.combined_dynamic_ports<>2
    THEN RAISE EXCEPTION 'Version resource baseline changed'; END IF;
    IF EXISTS (SELECT 1 FROM app_versions WHERE app_id=211
        AND version='5.2.4_2.0.15.0-6')
    THEN RAISE EXCEPTION 'Release already registered'; END IF;

    INSERT INTO app_versions (
        app_id,version,tag,enabled,is_default,changes,min_memory,min_cpus,
        deprecated,deprecation_message,created_at,updated_at,user_id,admin_only,
        memory,memory_swap,memory_reservation,cpus,init,privileged,cap_add,cap_drop,
        tcp_port_range,udp_port_range,tcp_dynamic_ports,udp_dynamic_ports,pids_limit,
        combined_port_range,combined_dynamic_ports,app_slots,image,
        custom_field_preinstall_description,custom_field_postinstall_description,installed_image_digest
    ) SELECT app_id,'5.2.4_2.0.15.0-6','5.2.4_2.0.15.0-6',1,0,
        $changes$Private torrents now keep seeding when qBittorrent's web interface is set to a language other than English. Appbox pauses public torrents once they finish downloading. The check that decides which torrents are public looked for an English tracker message and a few tracker address formats, so with a translated interface it could mistake a private torrent for a public one and stop it within two minutes of finishing. Trackers that put the passkey straight after /announce/, such as C411, were affected. The check now reads the private flag qBittorrent reports for each torrent, and public torrents are still paused when they complete. Torrents that were stopped stay stopped after the update, so select them and click Start. Your torrents, settings and the API address used by Sonarr, Radarr and similar apps stay the same when you update.$changes$,
        min_memory,min_cpus,0,NULL,now(),now(),2,1,
        memory,memory_swap,memory_reservation,cpus,init,privileged,cap_add,cap_drop,
        tcp_port_range,udp_port_range,tcp_dynamic_ports,udp_dynamic_ports,pids_limit,
        combined_port_range,combined_dynamic_ports,app_slots,image,
        custom_field_preinstall_description,custom_field_postinstall_description,'repo.cylo.net/qbittorrent@sha256:7694de6a270893380b81a682a9bbc7b27744d19326c9370681adc7f4e6bdd865'
        FROM app_versions WHERE id=baseline.id RETURNING id INTO new_id;
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>1 THEN RAISE EXCEPTION 'Expected one new version'; END IF;
    SELECT * INTO STRICT candidate FROM app_versions WHERE id=new_id;
    IF (to_jsonb(candidate)-ARRAY['id','version','tag','enabled','is_default','changes','deprecated','deprecation_message','created_at','updated_at','user_id','admin_only','installed_image_digest'])
        IS DISTINCT FROM
       (to_jsonb(baseline)-ARRAY['id','version','tag','enabled','is_default','changes','deprecated','deprecation_message','created_at','updated_at','user_id','admin_only','installed_image_digest'])
    THEN RAISE EXCEPTION 'Resource parity failed'; END IF;

    INSERT INTO customfields (
        type,relid,relid2,fname,display_name,fieldtype,description,default_value,
        required,options,regex,adminonly,sort_order,flex,customtable_editable,
        template_type,"minLength","maxLength",version,app_version_id,stable_id,
        condition_json,sensitive,revealable,"unique"
    ) SELECT type,relid,relid2,fname,display_name,fieldtype,description,default_value,
        required,options,regex,adminonly,sort_order,flex,customtable_editable,
        template_type,"minLength","maxLength",'5.2.4_2.0.15.0-6',new_id,stable_id,
        condition_json,sensitive,revealable,"unique"
        FROM customfields WHERE id IN (1491,1492) AND type='app' AND relid=211
            AND version=baseline.version AND app_version_id=baseline.id
            AND ((fname='PASSWORD' AND fieldtype='complexPassword')
                OR (fname='ENABLE_VUETORRENT' AND fieldtype='selector'));
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>2 THEN RAISE EXCEPTION 'Expected two version-specific fields'; END IF;
END;
$release$;
COMMIT;
