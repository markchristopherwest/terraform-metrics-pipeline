############################################################################
# One timestamp for the whole run.
#
# plantimestamp() is fixed at plan time and *known* during plan, so every
# report line of a run carries the identical "@timestamp" and the file
# contents are fully known before apply. (timestamp() would be unknown until
# apply, which is fine for local_file but makes plans noisier.)
#
# Terraform has no "epoch" function, so the epoch is derived from the
# RFC 3339 string with the days-from-civil algorithm (H. Hinnant). It is
# needed for "days since last login" style maths against Prisma's epoch-ms
# fields.
############################################################################

locals {
  now_rfc3339 = plantimestamp()

  _t_year   = tonumber(formatdate("YYYY", local.now_rfc3339))
  _t_month  = tonumber(formatdate("MM", local.now_rfc3339))
  _t_day    = tonumber(formatdate("DD", local.now_rfc3339))
  _t_hour   = tonumber(formatdate("hh", local.now_rfc3339))
  _t_minute = tonumber(formatdate("mm", local.now_rfc3339))
  _t_second = tonumber(formatdate("ss", local.now_rfc3339))

  _t_y   = local._t_month <= 2 ? local._t_year - 1 : local._t_year
  _t_era = floor(local._t_y / 400)
  _t_yoe = local._t_y - local._t_era * 400
  _t_mp  = local._t_month > 2 ? local._t_month - 3 : local._t_month + 9
  _t_doy = floor((153 * local._t_mp + 2) / 5) + local._t_day - 1
  _t_doe = local._t_yoe * 365 + floor(local._t_yoe / 4) - floor(local._t_yoe / 100) + local._t_doy

  now_epoch_days = local._t_era * 146097 + local._t_doe - 719468
  now_epoch      = local.now_epoch_days * 86400 + local._t_hour * 3600 + local._t_minute * 60 + local._t_second
  now_epoch_ms   = local.now_epoch * 1000

  ms_per_day = 86400000
}
