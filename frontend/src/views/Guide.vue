<template>
  <div class="page guide">
    <van-nav-bar title="使用指南" left-arrow fixed placeholder @click-left="goBack" />

    <!-- 头图 -->
    <div class="g-hero">
      <div class="g-hero-title">3D 打印服务 · 使用指南</div>
      <div class="g-hero-sub">从提交模型到领取成品，一共 6 步</div>
    </div>

    <!-- 流程步骤 -->
    <div class="g-section">
      <div class="g-card">
        <div v-for="(s, i) in steps" :key="i" class="step-row">
          <div class="step-rail">
            <div class="step-num" :style="{ background: s.color }">{{ i + 1 }}</div>
            <div v-if="i < steps.length - 1" class="step-line"></div>
          </div>
          <div class="step-body">
            <div class="step-title">{{ s.title }}</div>
            <div class="step-desc">{{ s.desc }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 配额规则 -->
    <div class="g-section">
      <div class="g-section-title">配额规则</div>
      <div class="g-card quota-cards">
        <div class="q-box">
          <div class="q-big">2 次</div>
          <div class="q-label">每学期免费额度</div>
        </div>
        <div class="q-plus">＋</div>
        <div class="q-box">
          <div class="q-big">1 次</div>
          <div class="q-label">上传反馈奖励</div>
        </div>
      </div>
      <div class="g-card g-tip">
        额度按学期自动刷新；打印完成后在申请详情里上传实物图或参赛照片，
        审核通过即奖励 1 次打印机会。
      </div>
    </div>

    <!-- 模型要求 -->
    <div class="g-section">
      <div class="g-section-title">模型要求</div>
      <div class="g-card">
        <div v-for="(r, i) in requirements" :key="i" class="req-row">
          <van-icon name="checked" color="#07c160" size="16" />
          <span class="req-text">{{ r }}</span>
        </div>
      </div>
    </div>

    <!-- 常见问题 -->
    <div class="g-section">
      <div class="g-section-title">常见问题</div>
      <van-collapse v-model="activeFaq" class="g-collapse">
        <van-collapse-item v-for="(f, i) in faqs" :key="i" :title="f.q" :name="i">
          <div class="faq-a">{{ f.a }}</div>
        </van-collapse-item>
      </van-collapse>
    </div>

    <!-- 联系我们 -->
    <div class="g-section">
      <div class="g-section-title">联系我们</div>
      <van-cell-group inset>
        <van-cell title="在线留言" icon="chat-o" label="工作时间内一般当天回复" is-link to="/chat" />
        <van-cell title="工作室邮箱" icon="mail-o" label="hrbust3d101@163.com" />
        <van-cell title="线下领取" icon="location-o" label="创新创业协会工作室（携带校园卡）" />
      </van-cell-group>
    </div>

    <TabBar />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import TabBar from '../components/TabBar.vue'

const router = useRouter()
// Tab 级页面：优先返回上一页，无历史时回首页（避免"进得来回不去"）
function goBack() {
  if (window.history.length > 1) router.back()
  else router.replace('/')
}

const activeFaq = ref([0])

const steps = [
  { title: '登录', desc: '学号 + 教务系统密码登录，无需注册。', color: '#2f6bff' },
  { title: '提交申请', desc: '首页点「立即申请打印」，填写联系方式、电子邮箱和打印用途（均为必填），上传 STL 模型文件。', color: '#1989fa' },
  { title: '等待审批', desc: '工作室一般在 24 小时内审批，结果会通过站内消息和邮箱通知你。', color: '#07c160' },
  { title: '打印制作', desc: '审批通过后进入打印队列，打印中可在申请详情查看进度。', color: '#ff976a' },
  { title: '领取成品', desc: '完成后带校园卡到创新创业协会工作室领取。', color: '#ee0a24' },
  { title: '反馈领奖励', desc: '上传实物图或参赛现场照片，审核通过奖励 1 次打印机会。', color: '#7232dd' },
]

const requirements = [
  '仅支持 STL 格式，单文件不超过 50MB',
  '模型尺寸建议不超过打印平台范围（单件 ≤ 150mm）',
  '壁厚不低于 2mm，避免破面、非流形等缺陷',
  '不涉及商业用途与侵权内容',
  '因模型自身问题导致打印失败的，责任由申请人承担',
]

const faqs = [
  { q: '申请多久会审批？', a: '工作日一般 24 小时内完成审批，结果通过站内消息（底部「消息」tab）和邮箱同时通知。' },
  { q: '可以指定颜色和材料吗？', a: '目前开放 PLA（FDM）材料，颜色可在申请的「特别说明」中备注，工作室将根据库存情况尽量满足。' },
  { q: '打印失败了怎么办？', a: '因模型自身问题（破面、非流形、结构不合理）导致的失败由申请人承担；工艺问题可与工作室联系协商重打。' },
  { q: '额度用完了怎么办？', a: '每学期 2 次为免费基础额度，打印完成后上传反馈可额外获得 1 次；学期结束后自动刷新。' },
  { q: '成品可以代领吗？', a: '原则上本人凭校园卡领取，代领需出示申请人校园卡照片并提前在留言中说明。' },
]
</script>

<style scoped>
.guide {
  padding-bottom: 70px;
}
.g-hero {
  padding: 34px 20px 30px;
  background: linear-gradient(135deg, #2f6bff, #6f9bff);
  color: #fff;
}
.g-hero-title {
  font-size: 21px;
  font-weight: 700;
}
.g-hero-sub {
  margin-top: 6px;
  font-size: 13px;
  opacity: 0.88;
}
.g-section {
  margin-top: 16px;
}
.g-section-title {
  padding: 0 20px 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1a2233;
}
.g-card {
  margin: 0 16px;
  padding: 16px 16px 8px;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 4px 16px rgba(20, 46, 104, 0.06);
}
.g-tip {
  margin-top: 10px;
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.7;
  color: #646566;
}

/* 步骤时间线 */
.step-row {
  display: flex;
  gap: 12px;
}
.step-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.step-num {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  display: grid;
  place-items: center;
}
.step-line {
  flex: 1;
  width: 2px;
  min-height: 26px;
  margin: 4px 0;
  background: #e8ecf5;
  border-radius: 2px;
}
.step-body {
  padding-bottom: 16px;
}
.step-title {
  font-size: 15px;
  font-weight: 600;
  color: #1a2233;
  padding-top: 3px;
}
.step-desc {
  margin-top: 4px;
  font-size: 13px;
  line-height: 1.7;
  color: #646566;
}

/* 配额 */
.quota-cards {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px;
}
.q-box {
  flex: 1;
  padding: 14px 8px;
  border-radius: 12px;
  background: #f2f6ff;
  text-align: center;
}
.q-big {
  font-size: 24px;
  font-weight: 700;
  color: #2f6bff;
}
.q-label {
  margin-top: 4px;
  font-size: 12px;
  color: #969799;
}
.q-plus {
  font-size: 20px;
  color: #969799;
}

/* 要求 */
.req-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 0 10px;
}
.req-text {
  font-size: 13px;
  line-height: 1.6;
  color: #323233;
}
.faq-a {
  font-size: 13px;
  line-height: 1.8;
  color: #646566;
}
.g-collapse {
  margin: 0 16px;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(20, 46, 104, 0.06);
}

/* 桌面端 */
@media (min-width: 768px) {
  .g-hero {
    padding: 48px 36px 40px;
  }
  .g-hero-title {
    font-size: 26px;
  }
  .g-section-title {
    padding: 0 36px 8px;
  }
}
</style>
