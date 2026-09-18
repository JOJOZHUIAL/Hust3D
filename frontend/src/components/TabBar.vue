<template>
  <van-tabbar route safe-area-inset-bottom>
    <van-tabbar-item replace to="/" icon="home-o">首页</van-tabbar-item>
    <van-tabbar-item replace to="/applications" icon="orders-o">我的申请</van-tabbar-item>
    <van-tabbar-item replace to="/profile" icon="user-o">我的</van-tabbar-item>
  </van-tabbar>
</template>

<script setup>
// 底部导航栏（路由模式），首页 / 我的申请 / 我的 三个主 tab 共用。
// 通过 van-tabbar 的 route 属性 + item 的 to 属性实现点击切换与高亮。
</script>
