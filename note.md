# VPS backend deploy (nomination vote fix)

```bash
cd /path/to/mh5
git pull origin main          # needs commit with nomination-roster-fix-5a0110a
bash scripts/deploy_vps_backend.sh
```

Verify after restart:

```bash
curl -s https://myhigh5.com/api/v1/build-info
# expect: "build_id":"nomination-roster-fix-5a0110a"

python3 backend/scripts/verify_nomination_vote_levels.py \
  --base-url https://myhigh5.com/api/v1 --round-id 21 --contest-id 7
# expect: 0 failure(s)
```
