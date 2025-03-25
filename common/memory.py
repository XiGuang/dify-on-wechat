from common.expired_dict import ExpiredDict
# 用户图片缓存
USER_IMAGE_CACHE = ExpiredDict(60 * 3)