<template>
  <a-config-provider :theme="antdTheme">
    <main class="app-shell" :class="themeName">
      <section class="topbar">
        <div>
          <h1>AI主播演唱助手</h1>
          <p>单曲导入、分轨试听、滚动歌词、跑调导出与 VST 离线处理</p>
        </div>
        <div class="topbar-actions">
          <a-segmented v-model:value="themeName" :options="themeOptions" />
          <a-button type="primary" :loading="importing">
            <template #icon><ImportOutlined /></template>
            导入歌曲
          </a-button>
        </div>
      </section>

      <section class="workspace">
        <aside class="library-pane">
          <div class="pane-head">
            <div>
              <span class="eyebrow">歌曲库</span>
              <h2>本地工程</h2>
            </div>
            <a-button shape="circle" title="扫描目录">
              <template #icon><ReloadOutlined /></template>
            </a-button>
          </div>

          <a-input-search
            v-model:value="searchText"
            placeholder="搜索歌曲、歌手或格式"
            disabled
          />

          <a-list class="song-list" :data-source="filteredSongs">
            <template #renderItem="{ item, index }">
              <a-list-item
                class="song-row"
                :class="{ active: index === selectedIndex }"
                @click="selectedIndex = index"
              >
                <a-list-item-meta>
                  <template #title>
                    <span>{{ item.title }}</span>
                  </template>
                  <template #description>
                    {{ item.format }} · {{ item.duration }} · {{ item.status }}
                  </template>
                </a-list-item-meta>
                <a-tag :color="item.ready ? 'success' : 'default'">
                  {{ item.ready ? '可播放' : '待处理' }}
                </a-tag>
              </a-list-item>
            </template>
          </a-list>

          <div class="stacked-actions">
            <a-button block>
              <template #icon><FolderOpenOutlined /></template>
              选择目录
            </a-button>
            <a-button block type="primary">
              <template #icon><CloudUploadOutlined /></template>
              导入单曲
            </a-button>
            <a-button block>
              <template #icon><FileTextOutlined /></template>
              导入歌词
            </a-button>
          </div>
        </aside>

        <section class="lyrics-pane">
          <div class="lyrics-header">
            <div>
              <span class="eyebrow">滚动歌词</span>
              <h2>{{ currentSong.title }}</h2>
            </div>
            <a-space>
              <a-tag color="processing">{{ selectedBackend }}</a-tag>
              <a-tag>{{ currentSong.format }}</a-tag>
            </a-space>
          </div>

          <div class="lyrics-window">
            <div
              v-for="(line, index) in lyrics"
              :key="`${line.time}-${line.text}`"
              class="lyric-line"
              :class="{ current: index === currentLyricIndex }"
            >
              <span class="time">{{ line.time }}</span>
              <span>{{ line.text }}</span>
            </div>
          </div>

          <a-alert
            banner
            type="info"
            show-icon
            message="提示：真实滚动需要同名 .lrc/.srt，或在导入时选择 faster-whisper 生成歌词。MP3/M4A/AAC 会先自动转码为内部 WAV。"
          />
        </section>

        <aside class="control-pane">
          <a-tabs v-model:activeKey="activeTab">
            <a-tab-pane key="playback" tab="播放">
              <div class="time-row">
                <span>{{ currentTime }}</span>
                <span>{{ totalTime }}</span>
              </div>
              <a-slider v-model:value="progress" :tooltip-open="false" />

              <div class="transport">
                <a-button type="primary" size="large" shape="circle" @click="togglePlay">
                  <template #icon>
                    <PauseOutlined v-if="playing" />
                    <CaretRightOutlined v-else />
                  </template>
                </a-button>
                <a-button size="large" shape="circle" @click="playing = false">
                  <template #icon><StopOutlined /></template>
                </a-button>
                <a-button size="large" shape="circle">
                  <template #icon><SoundOutlined /></template>
                </a-button>
              </div>

              <a-divider />

              <ControlSlider label="人声" v-model="vocalGain" suffix="%" />
              <ControlSlider label="伴奏" v-model="instrumentGain" suffix="%" />
              <ControlSlider label="主输出" v-model="masterGain" suffix=" dB" :min="-12" :max="3" />

              <a-space class="button-grid" wrap>
                <a-button :type="vocalMuted ? 'primary' : 'default'" @click="vocalMuted = !vocalMuted">
                  人声{{ vocalMuted ? '已静音' : '静音' }}
                </a-button>
                <a-button :type="instrumentMuted ? 'primary' : 'default'" @click="instrumentMuted = !instrumentMuted">
                  伴奏{{ instrumentMuted ? '已静音' : '静音' }}
                </a-button>
                <a-button disabled>真人唱功</a-button>
              </a-space>
            </a-tab-pane>

            <a-tab-pane key="export" tab="导出">
              <ControlSlider label="跑调强度" v-model="toneDrift" suffix="%" />
              <a-form layout="vertical">
                <a-form-item label="分离后端">
                  <a-select v-model:value="selectedBackend" :options="separatorOptions" />
                </a-form-item>
                <a-form-item label="歌词后端">
                  <a-select v-model:value="lyricsBackend" :options="lyricsOptions" />
                </a-form-item>
                <a-form-item label="主输出 VST">
                  <a-input :value="vstName" readonly />
                </a-form-item>
              </a-form>
              <a-space wrap>
                <a-button>
                  <template #icon><ApiOutlined /></template>
                  加载 VST
                </a-button>
                <a-button>移除</a-button>
                <a-button type="primary">
                  <template #icon><DownloadOutlined /></template>
                  导出 WAV
                </a-button>
              </a-space>
            </a-tab-pane>

            <a-tab-pane key="status" tab="状态">
              <a-timeline>
                <a-timeline-item color="green">已加载歌曲工程</a-timeline-item>
                <a-timeline-item color="green">已生成 vocal / instrumental</a-timeline-item>
                <a-timeline-item color="blue">等待播放或导出</a-timeline-item>
                <a-timeline-item color="gray">改词唱真实模型未接入</a-timeline-item>
              </a-timeline>
              <a-alert
                type="warning"
                show-icon
                message="未实现的功能会保持置灰。当前 Web 前端是美化层原型，后续需要接入 Python 桥接 API 才能替代桌面 QML。"
              />
            </a-tab-pane>
          </a-tabs>
        </aside>
      </section>
    </main>
  </a-config-provider>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, ref, resolveComponent } from 'vue';
import { theme } from 'ant-design-vue';
import {
  ApiOutlined,
  CaretRightOutlined,
  CloudUploadOutlined,
  DownloadOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  ImportOutlined,
  PauseOutlined,
  ReloadOutlined,
  SoundOutlined,
  StopOutlined,
} from '@ant-design/icons-vue';

type ThemeName = 'dark' | 'light';

const themeName = ref<ThemeName>('dark');
const themeOptions = [
  { label: '暗色', value: 'dark' },
  { label: '亮色', value: 'light' },
];

const antdTheme = computed(() => ({
  algorithm: themeName.value === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
  token: {
    colorPrimary: '#f04474',
    borderRadius: 8,
    fontFamily: 'Microsoft YaHei, Segoe UI, sans-serif',
  },
}));

const importing = ref(false);
const playing = ref(false);
const activeTab = ref('playback');
const selectedIndex = ref(0);
const progress = ref(36);
const vocalGain = ref(100);
const instrumentGain = ref(100);
const masterGain = ref(-3);
const toneDrift = ref(40);
const vocalMuted = ref(false);
const instrumentMuted = ref(false);
const selectedBackend = ref('preview');
const lyricsBackend = ref('preview');
const searchText = ref('');
const vstName = ref('未加载，仅导出时生效');

const songs = [
  { title: 'Call of silence', format: 'MP3', duration: '03:28', status: '已导入', ready: true },
  { title: '多远都要在一起', format: 'M4A', duration: '04:12', status: '已转码', ready: true },
  { title: '寂寞烟火', format: 'MP3', duration: '03:55', status: '可播放', ready: true },
  { title: '真人唱功实验', format: 'WAV', duration: '--:--', status: '待接入', ready: false },
];

const lyrics = [
  { time: '00:00', text: '等待前奏进入' },
  { time: '00:08', text: '那又如何' },
  { time: '00:15', text: '他好像爱我' },
  { time: '00:22', text: '可是我知道这只是想象' },
  { time: '00:31', text: '声音跟着节拍慢慢靠近' },
  { time: '00:40', text: '导入歌词后这里会自动滚动' },
  { time: '00:51', text: '跑调强度会影响导出的音频' },
];

const separatorOptions = [
  { label: 'preview（快速预览）', value: 'preview' },
  { label: 'demucs（真实分离）', value: 'demucs' },
];

const lyricsOptions = [
  { label: 'preview（占位歌词）', value: 'preview' },
  { label: 'faster-whisper（本地识别）', value: 'faster-whisper' },
  { label: 'none（不生成）', value: 'none' },
];

const filteredSongs = computed(() => {
  const keyword = searchText.value.trim().toLowerCase();
  if (!keyword) return songs;
  return songs.filter((song) => song.title.toLowerCase().includes(keyword));
});

const currentSong = computed(() => songs[selectedIndex.value] ?? songs[0]);
const currentLyricIndex = computed(() => Math.min(lyrics.length - 1, Math.floor(progress.value / 16)));
const currentTime = computed(() => `01:${String(Math.round(progress.value)).padStart(2, '0')}`);
const totalTime = computed(() => currentSong.value.duration);

function togglePlay() {
  playing.value = !playing.value;
}

const ControlSlider = defineComponent({
  props: {
    label: { type: String, required: true },
    suffix: { type: String, default: '' },
    min: { type: Number, default: 0 },
    max: { type: Number, default: 150 },
    modelValue: { type: Number, required: true },
  },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    const slider = resolveComponent('a-slider');
    return () =>
      h('div', { class: 'control-slider' }, [
        h('div', { class: 'control-label' }, [
          h('span', props.label),
          h('strong', `${props.modelValue}${props.suffix}`),
        ]),
        h(slider, {
          value: props.modelValue,
          min: props.min,
          max: props.max,
          tooltipOpen: false,
          onChange: (value: number) => emit('update:modelValue', value),
        }),
      ]);
  },
});
</script>
