"""Check openwakeword.data / utils API available in 0.4.0."""
import openwakeword.data as d, openwakeword.utils as u, inspect
print("data:", [a for a in dir(d) if not a.startswith('_')])
print("utils:", [a for a in dir(u) if not a.startswith('_')])
print("mix_clips_batch sig:", inspect.signature(d.mix_clips_batch))
print("filter_audio_paths sig:", inspect.signature(d.filter_audio_paths))
print("AudioFeatures methods:", [a for a in dir(u.AudioFeatures) if not a.startswith('_')])
print("embed_clips sig:", inspect.signature(u.AudioFeatures.embed_clips))
print("get_embedding_shape sig:", inspect.signature(u.AudioFeatures.get_embedding_shape))
