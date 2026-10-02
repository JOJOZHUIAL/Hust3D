<template>
  <van-tabbar route safe-area-inset-bottom>
    <van-tabbar-item replace to="/" icon="home-o">首页</van-tabbar-item>
    <van-tabbar-item replace to="/applications" icon="orders-o">我的申请</van-tabbar-item>
    <van-tabbar-item replace to="/notifications" icon="bell" :badge="unreadCount > 0 ? String(unreadCount) : undefined">消息</van-tabbar-item>
    <van-tabbar-item replace to="/profile" icon="user-o">我的</van-tabbar-item>
  </van-tabbar>
</template>

<script setup>
// 底部导航栏（路由模式）：首页 / 我的申请 / 消息（红点角标）/ 我的。
// 「消息」tab 显示全局未读通知数（store/notification.js，App.vue 每 8 秒轮询）。
import { unreadCount } from '../store/notification'
</script>
